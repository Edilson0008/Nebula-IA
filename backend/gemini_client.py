"""Cliente que isola toda a comunicação com a API do Gemini.

Se um dia trocarmos de provedor (ou rodarmos um modelo local), só este
arquivo muda — o resto do backend continua igual.

Duas defesas contra as "quedas" da API no plano gratuito:

1. LISTA DE MODELOS: a cota do plano gratuito é por modelo. Se um esgota, o
   cliente passa para o próximo da lista sem o usuário perceber.
2. RETENTATIVA COM ESPERA: erros passageiros (limite por minuto, 503,
   oscilação de rede) são tentados de novo com uma espera que vai crescendo,
   em vez de virarem erro na tela na primeira falha.
"""

import base64
from collections.abc import Callable, Iterator
from datetime import datetime
import json
import os
from pathlib import Path
import queue
import random
import threading
import time
from zoneinfo import ZoneInfo

from google import genai
from google.genai import types

# Erros que indicam "esse modelo não pode agora, tenta de novo ou tenta outro".
_TRANSIENT_MARKERS = (
    "resource_exhausted",
    "resource exhausted",
    "429",
    "unavailable",
    "503",
    "500",
    "502",
    "504",
    "overloaded",
    "quota",
    "deadline",
    "timeout",
    "timed out",
    "connection",
    "reset",
    "eof",
    "temporarily",
)

# Erros que significam "esse modelo não serve, descarta da lista".
_DEAD_MODEL_MARKERS = (
    "not_found",
    "not found",
    "no longer available",
    "not supported",
    "unsupported",
    "does not exist",
)

# Quantas rodadas completas pela lista de modelos antes de desistir.
_MAX_ROUNDS = 2

# Quantas vezes tentamos RETOMAR uma resposta cortada no meio (queda de
# conexão, cota do modelo, instabilidade). Sem isso, um site/código grande
# ficava pela metade quando o modelo era interrompido no meio da escrita.
_MAX_CONTINUACOES = 4

# De quanto em quanto tempo vale a pena reprovar um modelo que falhou.
# Cota diária: só volta à meia-noite (Pacífico); limite por minuto: segundos;
# instabilidade (503): um minuto; lentidão: alguns minutos. Sem isso o app
# repetia a lista inteira a cada mensagem e perdia 20 s antes de responder.
_MINUTE_COOLDOWN = 45.0
_BUSY_COOLDOWN = 60.0
_UNAVAILABLE_COOLDOWN = 20.0
_SLOW_COOLDOWN = 75.0

# Quanto esperar pelo PRIMEIRO pedaço antes de considerar o modelo travado.
# Conversa normal: 5 s (um bom modelo responde em ~1 s). Pedido com
# raciocínio (site/código) pode pensar mais antes de escrever.
_FIRST_TOKEN_TIMEOUT = 5.0
_FIRST_TOKEN_TIMEOUT_THINKING = 25.0
# Pausa máxima entre pedaços depois que a resposta começou.
_IDLE_TIMEOUT = 45.0

# Passo do agente (decidir qual ferramenta chamar) é curto: se o modelo não
# começa a responder nesse tempo, o próximo da lista assume.
_AGENT_STEP_TIMEOUT = 8.0

_PACIFIC = ZoneInfo("America/Los_Angeles")
_BRASILIA = ZoneInfo("America/Sao_Paulo")

# Chaves que, no erro da API, indicam cota DIÁRIA (esperar não resolve —
# melhor trocar de modelo na hora).
_DAILY_KEYS = ("perday", "per_day", "daily")
# Chaves que indicam cota POR MINUTO (esperar um pouco resolve).
_MINUTE_KEYS = ("perminute", "per_minute", "permin", "rpm")


def _flat(exc: Exception) -> str:
    """Texto do erro sem underscores/espaços, para comparar com segurança."""
    text = str(exc).lower()
    for char in ("_", " ", "-", "[", "]", "'", '"'):
        text = text.replace(char, "")
    return text


def is_transient(exc: Exception) -> bool:
    """True quando vale a pena tentar de novo (cota momentânea, instabilidade)."""
    text = str(exc).lower()
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def is_dead_model(exc: Exception) -> bool:
    """True quando o modelo não existe/foi desativado para esta conta."""
    flat = _flat(exc)
    return any(marker.replace("_", "") in flat for marker in _DEAD_MODEL_MARKERS)


def is_daily_limit(exc: Exception) -> bool:
    """True quando o limite é o diário (esperar segundos não adianta)."""
    flat = _flat(exc)
    if any(key in flat for key in _MINUTE_KEYS):
        return False
    return any(key in flat for key in _DAILY_KEYS)


def is_minute_limit(exc: Exception) -> bool:
    """True quando é o limite por minuto (esperar alguns segundos resolve)."""
    flat = _flat(exc)
    return any(key in flat for key in _MINUTE_KEYS)


def _chunk_text(chunk) -> str:
    """Texto de um pedaço da resposta (alguns pedaços não têm texto)."""
    try:
        return chunk.text or ""
    except Exception:  # noqa: BLE001 - pedaço sem partes de texto
        return ""


def _wait(round_index: int) -> float:
    """Espera progressiva com um pouco de aleatoriedade (1.5s, 3s, 6s...)."""
    delay = min(1.5 * (2**round_index), 12.0)
    return delay + random.uniform(0, 0.6)


def _next_daily_reset() -> float:
    """Instante (epoch) em que a cota diária do Google volta (meia-noite PT)."""
    agora = datetime.now(_PACIFIC)
    return time.time() + (24 * 3600 - (agora.hour * 3600 + agora.minute * 60 + agora.second)) + 120


def _iter_with_timeout(
    iterator: Iterator,
    first_timeout: float,
    idle_timeout: float = _IDLE_TIMEOUT,
) -> Iterator:
    """Itera a resposta do modelo com prazo para o primeiro pedaço.

    O SDK segura a conexão até o modelo começar a falar; um modelo
    sobrecarregado pode levar 20 s ou mais. Aqui o stream roda numa thread e
    a gente desiste se o primeiro pedaço não chegar a tempo — aí o cliente
    tenta o próximo modelo, em vez de deixar o usuário esperando.
    """
    fila: queue.Queue = queue.Queue()

    def trabalhadora() -> None:
        try:
            for item in iterator:
                fila.put(("pedaco", item))
            fila.put(("fim", None))
        except BaseException as exc:  # noqa: BLE001 - repassado ao consumidor
            fila.put(("erro", exc))

    threading.Thread(target=trabalhadora, daemon=True).start()

    primeiro = True
    while True:
        try:
            tipo, carga = fila.get(
                timeout=first_timeout if primeiro else idle_timeout
            )
        except queue.Empty:
            raise TimeoutError(
                "O modelo demorou demais para começar a responder."
            )
        if tipo == "pedaco":
            primeiro = False
            yield carga
        elif tipo == "fim":
            return
        else:
            raise carga


def _default_state_path() -> Path | None:
    """Onde guardar o que já sabemos sobre cada modelo (sobrevive a reinício)."""
    pastas = []
    if os.getenv("NEBULA_STATE_DIR"):
        pastas.append(Path(os.environ["NEBULA_STATE_DIR"]))
    pastas += [Path("/var/lib/nebula"), Path(__file__).resolve().parent]
    for pasta in pastas:
        try:
            pasta.mkdir(parents=True, exist_ok=True)
            teste = pasta / ".nebula-escrita"
            teste.write_text("ok", encoding="utf-8")
            teste.unlink()
            return pasta / "gemini-state.json"
        except Exception:  # noqa: BLE001 - pasta sem permissão: tenta a próxima
            continue
    return None


def _is_bad_request(exc: Exception) -> bool:
    """400 = a API recusou o pedido (ex.: ferramenta que o modelo não aceita)."""
    if getattr(exc, "code", None) == 400:
        return True
    text = str(exc)
    return "'code': 400" in text or '"code": 400' in text or "BAD_REQUEST" in text


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        models: list[str],
        embedding_model: str,
        memory_models: list[str] | None = None,
        image_models: list[str] | None = None,
        extra_api_keys: list[str] | None = None,
    ):
        # Várias keys do Google (contas diferentes) dividem a cota diária —
        # a de IMAGEM é pequena e vale por key, então rotação multiplica as
        # imagens (Nano Banana) que saem por dia.
        keys = [api_key] + [k for k in (extra_api_keys or []) if k and k != api_key]
        self._clients = [genai.Client(api_key=key) for key in keys]
        self._client = self._clients[0]  # conversa/memória: key principal
        self.models = models or ["gemini-3.8-flash"]
        self.model = self.models[0]  # modelo principal (o que aparece na tela)
        self.embedding_model = embedding_model
        # Modelos (mais leves) usados só para a memória. Em geral são cotas
        # separadas, então aprender fatos não gasta as conversas.
        self.memory_models = memory_models or self.models
        # Modelos de imagem: cota própria e curta (o app degrada para texto).
        self.image_models = image_models or []
        # Modelos que já deram erro de "não existe": não perdemos tempo com eles.
        self._dead: set[str] = set()
        # "Castigo" de cada modelo: modelo -> quando vale a pena tentar de novo.
        self._exhausted: dict[str, float] = {}
        # Tempo até o primeiro pedaço (ms), para colocar os rápidos na frente.
        self._ttft: dict[str, float] = {}
        # Último modelo que respondeu bem: é por ele que a próxima começa.
        self._last_ok: str | None = None
        self._day = datetime.now(_PACIFIC).date().isoformat()
        self._state_file = _default_state_path()
        self._state_lock = threading.Lock()
        self._state_saved_at = 0.0
        self._load_state()
        # Busca na web recusada pela conta (429 de plano): quando tentar de novo.
        # Enquanto isso, as mensagens seguem sem busca em vez de quebrarem.
        self._search_dead_until: float = 0.0

    # ------------------------------------------------------- estado/velocidade

    def _load_state(self) -> None:
        """Recupera o que aprendemos antes (modelo bom, lentos, castigos)."""
        if self._state_file is None:
            return
        try:
            dados = json.loads(self._state_file.read_text(encoding="utf-8"))
            self._state_saved_at = self._state_file.stat().st_mtime
        except Exception:  # noqa: BLE001 - primeiro uso ou arquivo corrompido
            return
        if not isinstance(dados, dict):
            return
        agora = time.time()
        castigos = dados.get("castigos") or {}
        if isinstance(castigos, dict):
            self._exhausted = {
                str(modelo): float(quando)
                for modelo, quando in castigos.items()
                if isinstance(quando, (int, float)) and quando > agora
            }
        tempos = dados.get("ttft") or {}
        if isinstance(tempos, dict):
            self._ttft = {
                str(modelo): float(ms)
                for modelo, ms in tempos.items()
                if isinstance(ms, (int, float)) and 0 < ms < 120_000
            }
        if dados.get("dia") == self._day:
            ultimo = dados.get("ultimo_bom")
            if isinstance(ultimo, str) and ultimo in self.models:
                self._last_ok = ultimo

    def _save_state(self) -> None:
        """Grava o estado (arquivo pequeno) para o próximo início ser rápido.

        Grava num arquivo temporário e troca de uma vez: assim uma queda no
        meio da escrita não deixa JSON pela metade, e funciona mesmo quando o
        arquivo antigo foi criado por outro usuário (basta a pasta permitir).
        """
        if self._state_file is None:
            return
        with self._state_lock:
            dados = {
                "castigos": self._exhausted,
                "ttft": self._ttft,
                "ultimo_bom": self._last_ok,
                "dia": self._day,
            }
            texto = json.dumps(dados, ensure_ascii=False)
            destinos = [self._state_file]
            alternativa = Path(__file__).resolve().parent / "gemini-state.json"
            if alternativa != self._state_file:
                destinos.append(alternativa)
            for destino in destinos:
                try:
                    temporario = destino.with_name(destino.name + ".tmp")
                    temporario.write_text(texto, encoding="utf-8")
                    os.replace(temporario, destino)
                    self._state_file = destino
                    self._state_saved_at = time.time()
                    return
                except Exception:  # noqa: BLE001 - estado é otimização
                    continue

    def _note_success(self, modelo: str, ttft_ms: float) -> None:
        """Anota que o modelo respondeu (e quão rápido) para priorizá-lo."""
        anterior = self._ttft.get(modelo)
        self._ttft[modelo] = (
            ttft_ms if anterior is None else 0.7 * anterior + 0.3 * ttft_ms
        )
        self._last_ok = modelo
        self._exhausted.pop(modelo, None)
        self._save_state()

    def _cool(self, modelo: str, segundos: float, motivo: str) -> None:
        """Tira o modelo de rotação por um tempo (sem repetir erro a cada msg)."""
        ate = time.time() + segundos
        if ate <= self._exhausted.get(modelo, 0.0):
            return
        self._exhausted[modelo] = ate
        hora = datetime.fromtimestamp(ate, _BRASILIA).strftime("%H:%M")
        print(f"[modelo] {modelo} {motivo}; volta por volta de {hora}.")
        self._save_state()

    def _cooling_message(self) -> str:
        """Aviso honesto quando todos os modelos estão de castigo."""
        agora = time.time()
        futuros = [quando for quando in self._exhausted.values() if quando > agora]
        if not futuros:
            return "Nenhum modelo disponível agora. Tente de novo em instantes."
        proximo = min(futuros)
        hora = datetime.fromtimestamp(proximo, _BRASILIA).strftime("%H:%M")
        if proximo - agora > 1800:
            return (
                "A cota gratuita de hoje acabou para todos os modelos. "
                f"Ela volta sozinha às {hora} (horário de Brasília)."
            )
        return (
            "Os modelos estão ocupados neste instante. "
            f"O próximo libera perto de {hora} (horário de Brasília)."
        )

    def _virada_do_dia(self) -> None:
        """Nova cota diária: volta a testar a partir do modelo principal."""
        hoje = datetime.now(_PACIFIC).date().isoformat()
        if hoje != self._day:
            self._day = hoje
            self._last_ok = None
            self._save_state()

    # ------------------------------------------------------------- conversa

    def _contents(
        self,
        history: list[dict],
        message: str,
        attachments: list[dict] | None = None,
    ) -> list[dict]:
        """Monta a conversa no formato que a API espera.

        history: [{"role": "user" | "model", "content": str}, ...]
        attachments: [{"mime_type": str, "data": bytes}, ...] da mensagem atual
        (imagens/arquivos vão como "inline_data", que é como o Gemini recebe
        mídia direto no corpo da requisição).
        """
        contents = [
            {"role": m["role"], "parts": [{"text": m["content"]}]} for m in history
        ]
        parts: list[dict] = [{"text": message or "Analise o anexo enviado."}]
        for item in attachments or []:
            parts.append(
                {
                    "inline_data": {
                        "mime_type": item["mime_type"],
                        "data": item["data"],
                    }
                }
            )
        contents.append({"role": "user", "parts": parts})
        return contents

    def _config(
        self,
        system_instruction: str,
        thinking_budget: int = 0,
        max_output_tokens: int = 8192,
        search: bool = False,
    ) -> types.GenerateContentConfig:
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.7,
            max_output_tokens=max_output_tokens,
        )
        try:
            if thinking_budget is not None and thinking_budget > 0:
                config.thinking_config = types.ThinkingConfig(
                    thinking_budget=thinking_budget,
                    include_thoughts=False,
                )
        except Exception:
            pass
        if search:
            # Busca na web (grounding): o modelo decide quando consultar e a
            # resposta chega com as fontes no grounding_metadata.
            try:
                config.tools = [types.Tool(google_search=types.GoogleSearch())]
            except Exception:
                pass
        return config

    def _live_models(
        self, models: list[str], tentados: set[str] | None = None
    ) -> list[str]:
        """Modelos que ainda vale a pena tentar, do mais promissor ao menos.

        `tentados` são os que já falharam NESTE pedido: não voltam na rodada
        seguinte (repetir um 503 segundos depois só gasta o tempo do usuário).

        Fora da lista: os que não existem/foram descartados e os que estão de
        "castigo" (cota diária, limite por minuto, instabilidade ou lentidão).
        Se todos estiverem de castigo, devolve lista vazia: avisar na hora é
        melhor do que gastar vinte segundos tentando um por um.
        """
        self._virada_do_dia()
        tentados = tentados or set()
        vivos = [m for m in models if m not in self._dead] or list(models)
        agora = time.time()
        frescos = [
            m
            for m in vivos
            if m not in tentados and self._exhausted.get(m, 0.0) <= agora
        ]

        def prioridade(modelo: str) -> tuple:
            # Quem respondeu por último vem primeiro; depois, o de menor tempo
            # até o primeiro pedaço já medido; por fim, a ordem do .env.
            preferido = 0 if modelo == self._last_ok else 1
            medido = self._ttft.get(modelo)
            return (
                preferido,
                medido if medido is not None else 10_000.0,
                models.index(modelo),
            )

        if frescos:
            return sorted(frescos, key=prioridade)

        # Todo mundo de castigo: se o primeiro a liberar está quase voltando,
        # tenta só ele em vez de já devolver erro. Um castigo curto não deve
        # virar uma parede na frente do usuário.
        castigados = [
            m
            for m in vivos
            if m not in tentados and self._exhausted.get(m, 0.0) > agora
        ]
        if not castigados:
            return []
        proximo = min(castigados, key=lambda m: self._exhausted.get(m, 0.0))
        if self._exhausted[proximo] - agora <= 60.0:
            return [proximo]
        return []

    def _note_daily_limit(self, model: str) -> None:
        """Marca cota diária esgotada até a virada do dia (Pacífico)."""
        segundos = max(60.0, _next_daily_reset() - time.time())
        self._cool(model, segundos, "esgotou a cota do dia")

    def warmup(self, max_age: float = 1800.0, first_timeout: float = 6.0) -> None:
        """Descobre, em segundo plano, qual modelo está respondendo agora.

        Roda no início do backend quando o estado guardado está velho: assim a
        primeira mensagem do usuário já começa no modelo certo, em vez de
        percorrer a lista inteira (o que levava 20 s).
        """
        if time.time() - self._state_saved_at < max_age:
            return
        for modelo in self.models:
            if modelo in self._dead:
                continue
            if self._exhausted.get(modelo, 0.0) > time.time():
                continue
            inicio = time.time()
            try:
                config = types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=8,
                )
                chunks = self._client.models.generate_content_stream(
                    model=modelo,
                    contents="ok",
                    config=config,
                )
                for _ in _iter_with_timeout(chunks, first_timeout, 10.0):
                    self._note_success(modelo, (time.time() - inicio) * 1000)
                    print(
                        f"[modelo] teste rápido: {modelo} respondeu em "
                        f"{(time.time() - inicio) * 1000:.0f} ms"
                    )
                    return
            except TimeoutError:
                self._cool(modelo, _SLOW_COOLDOWN, "lento no teste")
            except Exception as exc:  # noqa: BLE001 - teste nunca derruba o app
                if is_dead_model(exc):
                    self._dead.add(modelo)
                elif is_daily_limit(exc):
                    self._note_daily_limit(modelo)
                elif is_transient(exc):
                    self._cool(modelo, _BUSY_COOLDOWN, "ocupado no teste")
                else:
                    print(f"[modelo] teste de {modelo} falhou: {str(exc)[:100]}")

    def _handle_failure(self, model: str, exc: Exception) -> str:
        """Classifica uma falha: 'skip' (descarta o modelo), 'retry' ou 'raise'."""
        if is_dead_model(exc):
            self._dead.add(model)
            print(f"[modelo] {model} não está disponível nesta conta; descartando.")
            return "skip"
        if isinstance(exc, TimeoutError):
            # Fica ruim na fila mesmo depois que o castigo passar: foi lento
            # de verdade, não só um tropeço momentâneo.
            self._ttft[model] = max(self._ttft.get(model, 0.0), 6000.0)
            self._cool(model, _SLOW_COOLDOWN, "lento demais")
            return "retry"
        if not is_transient(exc):
            return "raise"
        if is_daily_limit(exc):
            return "retry"  # quem chama marca a cota diária
        texto = str(exc).lower()
        if "503" in texto or "unavailable" in texto or "overloaded" in texto:
            self._cool(model, _UNAVAILABLE_COOLDOWN, "sobrecarregado")
        elif is_minute_limit(exc):
            self._cool(model, _MINUTE_COOLDOWN, "limite por minuto")
        else:
            self._cool(model, _BUSY_COOLDOWN, "ocupado")
        return "retry"

    def generate(
        self,
        system_instruction: str,
        history: list[dict],
        message: str,
        attachments: list[dict] | None = None,
    ) -> tuple[str, str]:
        """Gera a resposta inteira. Devolve (texto, modelo_usado).

        Tenta cada modelo da lista e, se o problema for passageiro, espera um
        pouco e tenta a rodada toda de novo.
        """
        contents = self._contents(history, message, attachments)
        last_error: Exception | None = None
        tentados: set[str] = set()

        for round_index in range(_MAX_ROUNDS):
            waitable = False
            candidatos = self._live_models(self.models, tentados)
            if not candidatos:
                raise RuntimeError(self._cooling_message())

            for model in candidatos:
                tentados.add(model)
                try:
                    response = self._client.models.generate_content(
                        model=model,
                        contents=contents,
                        config=self._config(system_instruction, thinking_budget=0),
                    )
                    text = (response.text or "").strip()
                    if text:
                        self._note_success(model, 1000.0)
                        return text, model
                    last_error = RuntimeError("O modelo retornou uma resposta vazia.")
                    waitable = True
                except Exception as exc:  # noqa: BLE001 - classificamos abaixo
                    last_error = exc
                    verdict = self._handle_failure(model, exc)
                    if verdict == "skip":
                        continue
                    if verdict == "raise":
                        raise
                    if is_daily_limit(exc):
                        self._note_daily_limit(model)
                        continue  # esperar não resolve: melhor trocar de modelo
                    waitable = True
                    print(f"[modelo] {model} ocupado, tentando o próximo…")

            if not waitable:
                break
            if round_index < _MAX_ROUNDS - 1:
                delay = _wait(round_index)
                print(f"[modelo] todos ocupados; tentando de novo em {delay:.1f}s…")
                time.sleep(delay)

        raise last_error or RuntimeError("Nenhum modelo disponível.")

    def stream(
        self,
        system_instruction: str,
        history: list[dict],
        message: str,
        on_model: Callable[[str], None] | None = None,
        attachments: list[dict] | None = None,
        thinking_budget: int = 0,
        search: bool = False,
        on_sources: Callable[[list[dict]], None] | None = None,
        first_timeout: float | None = None,
    ) -> Iterator[str]:
        """Gera a resposta em pedaços, com troca de modelo e retentativa.

        A troca/retentativa só acontece antes do primeiro pedaço: depois que já
        começamos a mostrar a resposta, recomeçar duplicaria o texto.

        `first_timeout` é quanto esperar pelo primeiro pedaço: passou disso, o
        modelo é considerado travado e o próximo da lista assume. Sem valor,
        usa 7 s (conversa) ou 25 s (com raciocínio).

        thinking_budget > 0 (pedidos de site/código) liga o raciocínio interno:
        a resposta demora um pouco mais, mas vem melhor. Nesse caso o teto de
        saída sobe, porque os tokens de thinking descontam do mesmo limite.

        search=True liga a busca na web (grounding): o modelo consulta o
        Google quando precisa de informação atual e as fontes chegam pelo
        callback on_sources ([{"title": ..., "url": ...}]). Se a busca for
        recusada (ferramenta incompatível ou cota de plano), tentamos de novo
        sem ela e só voltamos a insistir daqui a meia hora — conversa nunca
        trava por causa de busca.
        """
        contents = self._contents(history, message, attachments)
        if search and time.time() < self._search_dead_until:
            search = False
        max_tokens = 16384 if thinking_budget else 8192
        config = self._config(
            system_instruction,
            thinking_budget=thinking_budget,
            max_output_tokens=max_tokens,
            search=search,
        )
        last_error: Exception | None = None
        if first_timeout is None:
            first_timeout = (
                _FIRST_TOKEN_TIMEOUT_THINKING
                if thinking_budget
                else _FIRST_TOKEN_TIMEOUT
            )

        # Fontes da busca (chegam no metadado dos pedaços, quase sempre no fim).
        sources: list[dict] = []
        seen_sources: set[str] = set()

        def collect_sources(chunk) -> None:
            if on_sources is None:
                return
            metadata = getattr(chunk, "grounding_metadata", None)
            if metadata is None:
                candidates = getattr(chunk, "candidates", None) or []
                if candidates:
                    metadata = getattr(candidates[0], "grounding_metadata", None)
            for item in getattr(metadata, "grounding_chunks", None) or []:
                web = getattr(item, "web", None)
                if web is None:
                    continue
                uri = getattr(web, "uri", None)
                if not uri or uri in seen_sources:
                    continue
                seen_sources.add(uri)
                sources.append(
                    {"title": getattr(web, "title", None) or uri, "url": uri}
                )
                on_sources(list(sources))

        tentados: set[str] = set()
        # Texto já produzido (para retomar de onde parou se a geração cair).
        partes: list[str] = []
        continuacoes = 0
        for round_index in range(_MAX_ROUNDS + _MAX_CONTINUACOES):
            waitable = False
            candidatos = self._live_models(self.models, tentados)
            if not candidatos and partes:
                # Já temos texto na tela: libera os modelos de novo para
                # conseguir RETOMAR em vez de deixar o site pela metade.
                tentados.clear()
                candidatos = self._live_models(self.models, tentados)
            if not candidatos:
                raise RuntimeError(self._cooling_message())

            for model in candidatos:
                tentados.add(model)
                produced = False
                search_retried = False
                retry_model = True

                # O "while" existe para um motivo só: se a busca na web for
                # recusada (400 de ferramenta ou 429 de cota de plano), tentamos
                # o MESMO modelo de novo sem a ferramenta.
                while retry_model:
                    retry_model = False
                    comecou = time.time()
                    try:
                        chunks = self._client.models.generate_content_stream(
                            model=model,
                            contents=contents,
                            config=config,
                        )

                        for chunk in _iter_with_timeout(
                            chunks, first_timeout, _IDLE_TIMEOUT
                        ):
                            collect_sources(chunk)
                            text = _chunk_text(chunk)
                            if not text:
                                continue
                            if not produced:
                                produced = True
                                self._note_success(
                                    model, (time.time() - comecou) * 1000
                                )
                                if on_model:
                                    on_model(model)
                            partes.append(text)
                            yield text
                        return

                    except Exception as exc:  # noqa: BLE001 - classificamos abaixo
                        last_error = exc

                        # Já mostramos texto: em vez de desistir (e deixar o
                        # site pela metade), pedimos para o próximo modelo
                        # CONTINUAR de onde paramos. Vale para cota do modelo,
                        # instabilidade e queda de conexão.
                        if produced:
                            # Cota (diária ou por minuto), instabilidade ou
                            # queda: em qualquer caso, retomar é melhor do que
                            # entregar o site pela metade.
                            pode_retomar = (
                                is_transient(exc)
                                or is_daily_limit(exc)
                                or _is_bad_request(exc)
                            )
                            if continuacoes < _MAX_CONTINUACOES and pode_retomar:
                                continuacoes += 1
                                produzido_antes = "".join(partes)
                                contents = contents + [
                                    {
                                        "role": "model",
                                        "parts": [{"text": produzido_antes}],
                                    },
                                    {
                                        "role": "user",
                                        "parts": [
                                            {
                                                "text": (
                                                    "Continue EXATAMENTE de onde parou. "
                                                    "Não repita nada do que já escreveu e "
                                                    "não comece de novo: siga direto do "
                                                    "ponto em que o texto foi cortado."
                                                )
                                            }
                                        ],
                                    },
                                ]
                                print(
                                    f"[modelo] {model} interrompeu; "
                                    f"retomando ({continuacoes}/{_MAX_CONTINUACOES})…"
                                )
                                break
                            raise

                        if search and not search_retried and (
                            _is_bad_request(exc) or is_transient(exc)
                        ):
                            # Busca indisponível nesta conta: tira, tenta sem
                            # ela agora e só volta a tentar em 30 minutos.
                            self._search_dead_until = time.time() + 1800
                            search = False
                            search_retried = True
                            config = self._config(
                                system_instruction,
                                thinking_budget=thinking_budget,
                                max_output_tokens=max_tokens,
                                search=False,
                            )
                            retry_model = True
                            continue

                        verdict = self._handle_failure(model, exc)
                        if verdict == "raise":
                            raise
                        if verdict == "skip":
                            break
                        if is_daily_limit(exc):
                            self._note_daily_limit(model)
                            # esperar não resolve: melhor trocar de modelo
                            break
                        waitable = True
                        print(f"[modelo] {model} ocupado, tentando o próximo…")
                        break

            if not waitable:
                break
            if round_index < _MAX_ROUNDS - 1:
                delay = _wait(round_index)
                print(f"[modelo] todos ocupados; tentando de novo em {delay:.1f}s…")
                time.sleep(delay)

        raise last_error or RuntimeError("Nenhum modelo disponível.")

    # ---------------------------------------------------------------- agente

    @staticmethod
    def _part_to_dict(part) -> dict:
        """Serializa uma parte da resposta preservando thought_signature.

        Com thinking ligado, a API exige que a assinatura volte junto nas
        partes (principalmente nas function_call) — reconstruir à mão perde
        ela e dá 400. Por isso preferimos o JSON cru do próprio SDK.
        """
        to_json = getattr(part, "to_json_dict", None)
        if callable(to_json):
            try:
                data = to_json()
                if isinstance(data, dict):
                    return {k: v for k, v in data.items() if v is not None}
            except Exception:  # noqa: BLE001 - cai no caminho manual
                pass
        data: dict = {}
        for key in ("text", "function_call", "function_response", "thought_signature"):
            value = getattr(part, key, None)
            if value is None:
                continue
            if key == "function_call":
                call = {"name": value.name, "args": dict(value.args or {})}
                if getattr(value, "id", None):
                    call["id"] = value.id
                data[key] = call
            else:
                data[key] = value
        return data

    @staticmethod
    def _parse_tool_response(parts) -> tuple[str | None, list[dict], list[dict]]:
        """Separa texto, chamadas e partes cruas (de uma resposta ou stream)."""
        texts: list[str] = []
        calls: list[dict] = []
        for part in parts or []:
            if part is None:
                continue
            piece = getattr(part, "text", None)
            if piece:
                texts.append(piece)
            fc = getattr(part, "function_call", None)
            if fc is not None and getattr(fc, "name", None):
                args = getattr(fc, "args", None) or {}
                try:
                    args = dict(args)
                except Exception:  # noqa: BLE001 - Struct estranho vira vazio
                    args = {}
                calls.append(
                    {
                        "id": getattr(fc, "id", "") or "",
                        "name": str(fc.name),
                        "args": args,
                    }
                )
        text = "".join(texts).strip() or None
        raw_parts = [d for d in (GeminiClient._part_to_dict(p) for p in parts or []) if d]
        return text, calls, raw_parts

    def tool_step(
        self,
        system_instruction: str,
        contents: list[dict],
        tools: list[dict],
        thinking_budget: int = 0,
    ) -> dict:
        """Um passo do agente: texto final e/ou chamadas de ferramenta.

        Devolve {"text": str|None, "calls": [{"id", "name", "args"}],
        "model": nome_do_modelo}. Usa a mesma defesa de cota e retentativa
        do generate(): se um modelo estiver sem cota, a lista inteira tenta
        o próximo sozinha.
        """
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.7,
            max_output_tokens=16384,
            tools=[types.Tool(function_declarations=tools)],
        )
        if thinking_budget > 0:
            try:
                config.thinking_config = types.ThinkingConfig(
                    thinking_budget=thinking_budget, include_thoughts=False
                )
            except Exception:  # noqa: BLE001 - thinking é opcional
                pass

        last_error: Exception | None = None
        tentados: set[str] = set()
        for round_index in range(_MAX_ROUNDS):
            waitable = False
            candidatos = self._live_models(self.models, tentados)
            if not candidatos:
                raise RuntimeError(self._cooling_message())

            for model in candidatos:
                tentados.add(model)
                comecou = time.time()
                try:
                    # Também em streaming: se o modelo travar antes de decidir
                    # a ferramenta, o próximo assume em vez de segurar a
                    # conversa por 10-20 s (era o passo mais lento do agente).
                    chunks = self._client.models.generate_content_stream(
                        model=model,
                        contents=contents,
                        config=config,
                    )
                    partes = []
                    for chunk in _iter_with_timeout(
                        chunks,
                        (
                            _FIRST_TOKEN_TIMEOUT_THINKING
                            if thinking_budget
                            else _AGENT_STEP_TIMEOUT
                        ),
                        _IDLE_TIMEOUT,
                    ):
                        candidatos_chunk = getattr(chunk, "candidates", None) or []
                        if not candidatos_chunk:
                            continue
                        conteudo = getattr(candidatos_chunk[0], "content", None)
                        partes.extend(getattr(conteudo, "parts", None) or [])
                except Exception as exc:  # noqa: BLE001 - classificamos abaixo
                    last_error = exc
                    verdict = self._handle_failure(model, exc)
                    if verdict == "skip":
                        continue
                    if verdict == "raise":
                        raise
                    if is_daily_limit(exc):
                        self._note_daily_limit(model)
                        continue
                    waitable = True
                    print(f"[agente] {model} ocupado, tentando o próximo…")
                    continue

                text, calls, raw_parts = self._parse_tool_response(partes)
                if text or calls:
                    self._note_success(model, (time.time() - comecou) * 1000)
                    return {
                        "text": text,
                        "calls": calls,
                        "model": model,
                        # Partes cruas: o laço as reenvia preservando a
                        # thought_signature exigida pela API com thinking.
                        "parts": raw_parts,
                    }
                last_error = RuntimeError("O modelo retornou uma resposta vazia.")
                waitable = True

            if not waitable:
                break
            if round_index < _MAX_ROUNDS - 1:
                delay = _wait(round_index)
                print(f"[agente] todos ocupados; tentando de novo em {delay:.1f}s…")
                time.sleep(delay)

        raise last_error or RuntimeError("Nenhum modelo disponível.")

    # ----------------------------------------------------------------- imagem

    def generate_image(self, prompt: str) -> bytes | None:
        """Gera uma imagem (Nano Banana e cia.) e devolve os bytes, ou None.

        A cota de imagem é separada — e bem curta — da de texto, e vale POR
        KEY: por isso tentamos todas as keys configuradas antes de desistir.
        Se todos os modelos/keys falharem, devolve None e o chamador cai para
        outro provedor (Cloudflare / Pollinations / texto), sem travar nada.
        """
        for index, client in enumerate(self._clients):
            for model in self._live_models(self.image_models):
                try:
                    response = client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_modalities=["TEXT", "IMAGE"],
                            max_output_tokens=8192,
                        ),
                    )
                    edited = self._extract_image(response)
                    if edited is not None:
                        return edited
                except Exception as exc:  # noqa: BLE001 - cota/404: tenta o próximo
                    key = f" key{index + 1}" if len(self._clients) > 1 else ""
                    print(f"[imagem]{key} {model}: {str(exc)[:140]}")
                    continue
        return None

    @staticmethod
    def _extract_image(response) -> bytes | None:
        """Puxa os bytes da imagem numa resposta do Gemini (geração ou edição)."""
        candidates = getattr(response, "candidates", None) or []
        candidate = candidates[0] if candidates else None
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            if inline is None or not inline.data:
                continue
            data = inline.data
            if isinstance(data, str):  # SDK devolve base64 às vezes
                data = base64.b64decode(data)
            return bytes(data)
        return None

    def edit_image(
        self, image_bytes: bytes, mime: str, instruction: str
    ) -> bytes | None:
        """Edita uma imagem existente seguindo a instrução (Nano Banana).

        Envia a foto + o pedido ("mude o fundo pra vermelho") e devolve a
        imagem editada. Mantém o resto da cena — é o trunfo do Nano Banana.
        Cota separada (e curta) da de texto; roda por todas as keys. None
        quando todos os modelos/keys falham (o chamador cai pra outro).
        """
        for index, client in enumerate(self._clients):
            for model in self._live_models(self.image_models):
                try:
                    response = client.models.generate_content(
                        model=model,
                        contents=[
                            types.Part.from_bytes(data=image_bytes, mime_type=mime),
                            instruction,
                        ],
                        config=types.GenerateContentConfig(
                            response_modalities=["TEXT", "IMAGE"],
                            max_output_tokens=8192,
                        ),
                    )
                    edited = self._extract_image(response)
                    if edited is not None:
                        return edited
                except Exception as exc:  # noqa: BLE001 - cota/404: tenta o próximo
                    key = f" key{index + 1}" if len(self._clients) > 1 else ""
                    print(f"[imagem-edit]{key} {model}: {str(exc)[:140]}")
                    continue
        return None

    def enhance_image_prompt(self, prompt: str) -> str | None:
        """Reescreve o pedido como prompt rico de imagem (inglês + detalhes).

        Flux/SANA/Nano Banana rendem MUITO mais com assunto + estilo +
        iluminação + enquadramento explícitos, em inglês. Se nenhum modelo de
        texto responder a tempo, devolve None e o chamador usa o pedido cru.
        """
        instruction = (
            "Você escreve prompts para geradores de imagem. Reescreva o pedido "
            "abaixo em inglês, em UMA ou DUAS frases densas: assunto, ação, "
            "estilo (cinematic photo, digital illustration, 3D render...), "
            "iluminação, enquadramento, clima e qualidade. Responda SOMENTE o "
            f"prompt, sem aspas nem explicação.\n\nPedido: {prompt}"
        )
        for client in self._clients:
            for model in self._live_models(self.models):
                try:
                    config = types.GenerateContentConfig(
                        temperature=0.9,
                        max_output_tokens=160,
                    )
                    try:
                        config.thinking_config = types.ThinkingConfig(
                            thinking_budget=0, include_thoughts=False
                        )
                    except Exception:
                        pass
                    response = client.models.generate_content(
                        model=model,
                        contents=instruction,
                        config=config,
                    )
                    text = (getattr(response, "text", "") or "").strip().strip('"')
                    if text and len(text) <= 800:
                        return text
                except Exception:
                    continue
        return None

    # --------------------------------------------------------------- memória

    def embed(
        self, text: str, task_type: str = "RETRIEVAL_DOCUMENT"
    ) -> list[float]:
        """Transforma um texto em vetor (para a memória de longo prazo).

        Usa tipos diferentes para o que é guardado (documento) e para a
        pergunta (consulta) — isso melhora bastante a busca.
        """
        last_error: Exception | None = None

        for attempt in range(2):
            try:
                response = self._client.models.embed_content(
                    model=self.embedding_model,
                    contents=text,
                    config=types.EmbedContentConfig(task_type=task_type),
                )
                if not response.embeddings:
                    raise RuntimeError("Não foi possível gerar o embedding.")
                return list(response.embeddings[0].values)
            except Exception as exc:  # noqa: BLE001 - classificamos abaixo
                last_error = exc
                if not is_transient(exc):
                    raise
                if attempt == 0:
                    time.sleep(_wait(0))

        raise last_error or RuntimeError("Não foi possível gerar o embedding.")

    def extract_memories(self, message: str, reply: str) -> list[str]:
        """Descobre fatos duradouros sobre o usuário nesta troca de mensagens."""
        prompt = (
            "Abaixo está uma troca de mensagens entre um usuário e uma assistente.\n"
            "Extraia SOMENTE fatos duradouros sobre o usuário que valham a pena "
            "lembrar em conversas futuras (nome, idade, cidade, trabalho, estudo, "
            "gostos, projetos, objetivos, preferências, restrições).\n\n"
            "Regras:\n"
            "- Ignore perguntas pontuais, curiosidades e assuntos temporários.\n"
            "- Cada fato deve ser uma frase curta e autossuficiente, começando "
            "com 'O usuário' ou com o nome da pessoa (nunca 'ele'/'ela').\n"
            "  Exemplo: 'O usuário é vegetariano.' / 'Bruno mora em Curitiba.'\n"
            "- Nada de suposições: só o que o usuário afirmou.\n"
            "- No máximo 3 fatos. Se não houver nada duradouro, devolve lista vazia.\n\n"
            f"USUÁRIO: {message}\n\n"
            f"ASSISTENTE: {reply}\n\n"
            'Responda SOMENTE com JSON neste formato: {"memorias": ["fato 1", "fato 2"]}'
        )

        raw = self._generate_json(prompt)
        if not raw:
            return []

        import json

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []

        facts = data.get("memorias") if isinstance(data, dict) else data
        if not isinstance(facts, list):
            return []

        cleaned = []
        for fact in facts:
            if isinstance(fact, str) and fact.strip():
                cleaned.append(fact.strip())
        return cleaned

    def _generate_json(self, prompt: str) -> str:
        """Pede uma resposta em JSON, com troca de modelo e retentativa."""
        last_error: Exception | None = None
        tentados: set[str] = set()

        for round_index in range(_MAX_ROUNDS):
            waitable = False
            candidatos = self._live_models(self.memory_models, tentados)
            if not candidatos:
                raise RuntimeError(self._cooling_message())

            for model in candidatos:
                tentados.add(model)
                try:
                    response = self._client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            temperature=0,
                            response_mime_type="application/json",
                        ),
                    )
                    return (response.text or "").strip()
                except Exception as exc:  # noqa: BLE001 - classificamos abaixo
                    last_error = exc
                    verdict = self._handle_failure(model, exc)
                    if verdict == "skip":
                        continue
                    if verdict == "raise":
                        raise
                    if is_daily_limit(exc):
                        self._note_daily_limit(model)
                        continue
                    waitable = True

            if not waitable:
                break
            if round_index < _MAX_ROUNDS - 1:
                time.sleep(_wait(round_index))

        raise last_error or RuntimeError("Nenhum modelo disponível.")
