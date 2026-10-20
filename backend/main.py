"""Backend da Nébula — FastAPI + Gemini."""

import base64
import io
import json
import os
import re
import threading
import zipfile
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import unquote

from dotenv import dotenv_values

PLACEHOLDER_KEYS = {"sua_chave_aqui", "your_api_key_here", "changeme"}

# Este projeto vive em dois lugares:
#   1. esta pasta                 -> onde o servidor roda (tem venv/ e node_modules/)
#   2. /sdcard/Download/minha-ia  -> copia acessivel pelo gerenciador de arquivos do celular
# A copia do celular tem PRIORIDADE, para que editar a chave por la funcione.
# Valores de exemplo (ex.: "sua_chave_aqui") sao ignorados.
ENV_CANDIDATES = [
    Path(__file__).parent / ".env",
    Path(os.getenv("GEMINI_ENV_FILE", "/sdcard/Download/minha-ia/backend/.env")),
]


def _load_env() -> None:
    values: dict[str, str] = {}
    for path in ENV_CANDIDATES:
        if not path.is_file():
            continue
        for key, value in dotenv_values(path).items():
            if not value:
                continue
            if key == "GEMINI_API_KEY" and value.strip().lower() in PLACEHOLDER_KEYS:
                continue
            values[key] = value
    os.environ.update(values)


_load_env()

from fastapi import FastAPI, HTTPException, Header, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import agent
import backup
import cf_image
import db_supabase as db
import design_guide
import memory
import pollinations
import realtime
import workspace
from gemini_client import GeminiClient

DEFAULT_SYSTEM_PROMPT = (
    "Você é a Nébula, uma assistente geral, prestativa e objetiva.\n"
    "- Seu nome é Nébula: apresente-se assim quando for natural.\n"
    "- Responda sempre em português do Brasil, a menos que o usuário escreva em outro idioma.\n"
    "- Prefira respostas claras e bem organizadas (use listas e passos quando ajudar).\n"
    "- Se algo for incerto, diga honestamente em vez de inventar.\n"
    "- Use markdown simples: negrito, listas e blocos de código quando fizer sentido.\n"
    "- Só afirme como fato o que você conseguir consultar agora (notícia, preço, "
    "resultado, horário). Se não tiver como consultar, diga isso em uma frase e "
    "sugira pedir 'notícias de hoje', 'clima em X' ou 'busca por Y' — nunca "
    "invente data, número ou manchete."
)

# ---------------------------------------------------------------------------
# "Sala" da pessoa: cada um vê só as próprias conversas.
#
# O site manda o apelido escolhido no cabeçalho X-Nebula-Sala. Sem ele, usa
# "local" (compatível com quem já usava antes). O apelido é saneado: só letras,
# números, ponto, hífen e underline.
# ---------------------------------------------------------------------------
def _sala(x_nebula_sala: str | None = Header(default=None)) -> str:
    bruto = (x_nebula_sala or "local").strip().lower()
    limpo = re.sub(r"[^a-z0-9._-]", "", bruto)[:40]
    return limpo or "local"


FILE_INSTRUCTIONS = (
    "\n\nCRIAÇÃO DE ARQUIVOS:\n"
    "Quando o usuário pedir um site, página, app, script, documento ou qualquer\n"
    "arquivo, crie os arquivos de verdade (não apenas mostre o código). Use sempre\n"
    "este formato, um bloco por arquivo:\n\n"
    "```file:index.html\n"
    "<!doctype html>\n"
    "...conteúdo completo do arquivo...\n"
    "```\n\n"
    "Regras:\n"
    "- Sempre comece o bloco com ```file: e termine com ```.\n"
    "- Conteúdo COMPLETO e pronto para uso (não use ... ou comentários de 'resto do código').\n"
    "- Nomes simples e relativos (index.html, style.css, script.js, app.py...).\n"
    "- Num site, crie index.html e ligue ao style.css (e script.js se precisar).\n"
    "- Não coloque os arquivos em blocos ``` comuns; use ```file:nome.\n"
    "- Fora dos blocos, escreva no máximo 2 frases explicando o que foi criado.\n"
    "- NUNCA escreva link de imagem (![..](/files/..)): as imagens geradas são\n"
    "  anexadas pelo sistema. Se um pedido de imagem não puder ser atendido,\n"
    "  diga em texto que não conseguiu — jamais invente um link.\n"
    "- Se o pedido não envolver arquivos, ignore estas regras e responda normalmente."
)

# "System prompt mestre" de front-end (nível Vercel/Stripe). Entra só em pedidos
# de site/página/app e sobe junto com o thinking — é o que faz a saída competir
# com site feito à mão em vez do visual genérico de IA.
def _design_rules(offline: bool, fotos: list[dict] | None = None) -> str:
    """O prompt mestre em duas versões: online (CDN) ou modo off (sem rede).

    O acabamento exigido é o mesmo nas duas; o que muda é a stack — no modo
    off nada pode ser carregado da internet, para o site abrir em qualquer
    lugar (sem sinal, no avião, aberto direto do arquivo).
    """
    stack = (
        "1. MODO OFF — a página tem que abrir 100% sem internet: PROIBIDO qualquer CDN\n"
        "   ou requisição externa (nada de cdn.tailwindcss.com, Google Fonts, unpkg,\n"
        "   imagens remotas). Entregue style.css artesanal e completo ligado no index.html,\n"
        "   fontes do sistema (system-ui), ícones e arte em SVG inline ou CSS puro, e o JS\n"
        "   em script.js — confira que nada é carregado da rede.\n"
        if offline
        else
        '1. Tailwind CSS via CDN primeiro: <script src="https://cdn.tailwindcss.com"></script>\n'
        "   no <head>, com tailwind.config inline quando precisar de cores/fontes próprias.\n"
        "   Fonte padrão: 'Inter' via Google Fonts (<link rel=\"preconnect\"> + a folha da\n"
        "   Inter), com fallback system-ui; um par display+corpo quando o projeto pedir\n"
        "   personalidade. style.css só para o que o Tailwind não cobre (keyframes,\n"
        "   scrollbar, prefers-*) e script.js para interações (menu hambúrguer, abas,\n"
        "   reveal no scroll).\n"
    )
    icons = (
        "3. Ícones SOMENTE em SVG inline (traço 1.5-2px) que você mesmo desenha — no modo\n"
        "   off não existe CDN de ícones nem foto remota (a página precisa abrir sem internet):\n"
        "   NUNCA links externos; arte visual em CSS/SVG e a página fica linda sem foto.\n"
        if offline
        else
        "3. MÍDIA E IMAGENS — regras obrigatórias:\n"
        "   - NUNCA invente URL de imagem nem link aleatório da internet, e NUNCA\n"
        "     use um serviço de imagem dinâmica por termo (picsum, source.unsplash,\n"
        "     placehold.co, loremflickr): esses endereços quebram e deixam a página\n"
        "     com imagem vazia. URL de imagem só sai da lista abaixo.\n"
        "   - ÍCONES: nunca use <img> para ícone. Use Lucide (ou FontAwesome) via CDN\n"
        "     ou SVG inline; ícone é sempre traço/vetor, nunca foto.\n"
        "   - Cada imagem tem de corresponder ESTRITAMENTE ao assunto específico do\n"
        "     bloco/seção onde ela entra. Card de leão → foto de leão; card de\n"
        "     tecnologia → foto de computador/código. Se a foto não for daquilo,\n"
        "     NÃO use: é melhor ilustrar o bloco em SVG/CSS.\n"
        "   - Blocos com assuntos DIFERENTES entre si (um card para cada animal:\n"
        "     leão, elefante, tigre…; um card por produto): a lista de fotos abaixo\n"
        "     pode não cobrir cada um. Antes de escrever o código, chame a ferramenta\n"
        "     `imagens` UMA VEZ POR ASSUNTO (tema=\"leão\", tema=\"elefante\"…) e use a\n"
        "     foto certa em cada bloco. Nunca reaproveite a foto de um assunto no card\n"
        "     de outro.\n"
        "   - Use SOMENTE as URLs da lista FOTOS REAIS (Openverse + Wikimedia\n"
        "     Commons, licença livre). Copie a URL EXATA, uma foto por seção, sem repetir a mesma foto.\n"
        "     Faltou foto para um item? Deixe esse item em SVG/CSS — repetir a MESMA\n"
        "     foto, ou usar uma fora do contexto, é pior que não ter foto ali.\n"
        "   - Toda <img> leva classes w-full h-48 object-cover rounded-xl (ou o\n"
        "     tamanho que a seção pedir, sempre com object-cover e raio), alt\n"
        "     descritivo e coerente em PORTUGUÊS (dizendo o que a foto mostra\n"
        "     naquele item), loading=\"lazy\", width/height; onerror esconde a foto e\n"
        "     mostra um fundo CSS/SVG.\n"
        "   - Se a lista não vier (ou nenhuma foto combinar), use SVG/CSS inline:\n"
        "     melhor sem foto do que com foto genérica ou desconexa.\n"
    )
    identity = (
        "6. Identidade própria: paleta, tipografia e raios declarados em variáveis CSS\n"
        "   (:root). Nada do clichê 'gradiente roxo-azul centralizado + dois botões iguais'.\n"
        "   Fontes do sistema (system-ui), escala fluida com clamp(), tracking negativo\n"
        "   nos títulos grandes e medida de leitura ~65ch.\n"
        if offline
        else
        "6. Identidade própria: paleta, tipografia e raios declarados no tailwind.config\n"
        "   (ou :root). Base de contraste limpo (fundo claro tipo slate-50/zinc-50 ou\n"
        "   escuro tipo zinc-900/slate-900 com texto claro) e UM acento — nada do clichê\n"
        "   'gradiente roxo-azul centralizado + dois botões iguais'. Evite excesso de\n"
        "   cor saturada. Google Fonts com par display+corpo (padrão Inter), escala\n"
        "   fluida com clamp(), tracking negativo nos títulos grandes e medida de\n"
        "   leitura ~65ch.\n"
    )
    regras = (
        "\n\nPERFIL OBRIGATÓRIO — VOCÊ É UM FRONT-END SÊNIOR (nível Vercel/Stripe):\n"
        "Ao criar site, página ou app, aja como um dev sênior de front-end: obsessivo\n"
        "por tipografia, espaçamento, estados de interação e animação. Entregue algo\n"
        "que não pareça gerado por IA. Regras obrigatórias:\n"
        + stack
        + "2. Mobile-first de verdade, testando mentalmente cada bloco de 360px (celular\n"
        "   pequeno) até 1920px (desktop). Em 360px nada estoura: sem rolagem horizontal,\n"
        "   alvos de toque ≥44px, imgs/svgs com max-width:100%, nav vira menu hambúrguer.\n"
        + icons
        + "4. Dados realísticos: PROIBIDO lorem ipsum. Todo conteúdo mockado é criativo,\n"
        "   completo e em pt-BR (nomes, preços, depoimentos, FAQs e números plausíveis,\n"
        "   coerentes entre si — nada de 'Item 1' ou 'texto de exemplo').\n"
        "5. Código 100% íntegro: sem resumos, sem pseudocódigo, sem '...' e sem\n"
        "   '// resto do código'. Os blocos ```file: saem completos, prontos para abrir.\n"
        + identity
        + "7. Página completa: header sticky com âncoras suaves, hero (eyebrow + título forte +\n"
        "   subtítulo + 2 CTAs), seções com cards, FAQ e rodapé. hover/focus-visible em tudo,\n"
        "   transições de 150-220ms, contraste AA, prefers-reduced-motion, favicon SVG inline,\n"
        "   meta description + og: e dark mode via prefers-color-scheme quando couber.\n"
        "8. A primeira dobra é o teste: o hero tem que parecer um site profissional de verdade."
    )
    if fotos and not offline:
        regras += (
            "\n\nFOTOS REAIS DISPONÍVEIS (copie a URL EXATA; não invente outra).\n"
            "Cada foto é de UM assunto — coloque cada uma só na seção cujo texto\n"
            "fala DAQUELE assunto (o nome diz do que é a foto):\n"
            + "".join(f"- {foto['url']} — {foto['titulo']}\n" for foto in fotos)
            + "Não repita foto e não encaixe foto que não bate com o item. O que\n"
            "sobrar sem foto combinando vira SVG/CSS.\n"
        )
    else:
        regras += (
            "\n\nSEM LISTA DE FOTOS NESTE PEDIDO: se um bloco precisa da imagem de um\n"
            "assunto específico (leão, pizza, prato, produto, pessoa), NÃO desista,\n"
            "NÃO use quadrado cinza nem URL genérica:\n"
            "1. Antes de responder, chame a ferramenta `imagens` com o tema do bloco\n"
            "   (ex.: tema=\"leão\", tema=\"pizza\") e use as URLs que ela devolver em\n"
            "   <img> — cada URL só no bloco do assunto dela.\n"
            "2. Se ela devolver URLs, use-as com alt descritivo em pt-BR.\n"
            "3. Só se a ferramenta não tiver nada daquele assunto, caia para SVG/CSS\n"
            "   bem desenhado (nunca um retângulo vazio nem foto fora do contexto).\n"
            "PROIBIDO dizer que você \"não consegue gerar ou buscar imagens\" (é falso:\n"
            "a ferramenta `imagens` existe) e PROIBIDO usar URL dinâmica de banco de\n"
            "imagens (picsum, source.unsplash, placehold.co) ou mandar o usuário buscar\n"
            "foto em Unsplash/Pexels — resolva você mesmo com URLs que existem.\n"
        )
    # Manual de agência (destilado de 300+ agentes especialistas da biblioteca
    # guias/): entra em todo pedido de build e é o que leva o acabamento do
    # "site de IA" para o nível de agência.
    regras += design_guide.PLAYBOOK
    return regras

MEMORY_HEADER = (
    "\n\nMEMÓRIA DE LONGO PRAZO (coisas que você já sabe sobre o usuário):\n"
)
MEMORY_FOOTER = (
    "\nUse essas informações apenas quando forem úteis para a resposta atual. "
    "Não liste tudo de novo nem diga 'segundo minha memória'."
)

SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT)


def _model_list(primary: str, extra: str) -> list[str]:
    """Junta o modelo principal com a lista de reservas, sem repetir."""
    names = [primary]
    for name in extra.replace(";", ",").split(","):
        name = name.strip()
        if name and name not in names:
            names.append(name)
    return names


# Modelo principal das conversas.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
# Reservas usadas quando a cota do principal acaba (a cota é por modelo, então
# trocar de modelo é como "ganhar" mais mensagens no plano gratuito).
# Só entram aqui modelos que existem de verdade para contas novas — os da
# família 2.5, por exemplo, respondem 404 hoje em dia.
GEMINI_FALLBACKS = os.getenv(
    "GEMINI_FALLBACK_MODELS",
    "gemini-3.7-flash,gemini-3.6-flash,gemini-3.5-flash,"
    "gemini-3.5-flash-lite,gemini-3.1-flash-lite",
)
GEMINI_MODELS = _model_list(GEMINI_MODEL, GEMINI_FALLBACKS)

EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
# Modelos leves só para aprender/lembrar fatos (cota separada das conversas).
MEMORY_MODELS = _model_list(
    os.getenv("GEMINI_MEMORY_MODEL", "gemini-3.1-flash-lite"),
    os.getenv("GEMINI_MEMORY_FALLBACK_MODELS", "gemini-3.5-flash-lite"),
)

# Modelos de imagem para "gere uma imagem de um gato". A cota é separada (e
# curta) da de texto: se todos estiverem esgotados, respondemos em texto.
IMAGE_MODELS = _model_list(
    os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image"),
    os.getenv(
        "GEMINI_IMAGE_FALLBACK_MODELS",
        "gemini-3.1-flash-lite-image,gemini-3.1-flash-image-preview,"
        "gemini-3-pro-image,gemini-2.5-flash-image",
    ),
)

# Pedidos de site/código "pensam" antes de escrever (qualidade); o resto
# responde direto, na velocidade máxima — um "oi" não precisa raciocinar.
THINKING_BUDGET_BUILD = int(os.getenv("GEMINI_THINKING_BUDGET_BUILD", "1024"))

# ------------------------------------------------------------------ agente
# Modo agente: a IA lê/escreve arquivos e EXECUTA comandos (terminal) até a
# tarefa ficar pronta — compilar APK, rodar testes, instalar dependências...
# Desligue com AGENT_ENABLED=0 no backend/.env.
AGENT_ENABLED = os.getenv("AGENT_ENABLED", "1").strip().lower() not in {
    "0",
    "false",
    "no",
}

# Quando o pedido pede ferramentas de verdade (compilar, instalar, rodar...).
# Pedidos comuns ("o que é X?") seguem o caminho normal, com streaming ao vivo.
# O que leva a conversa para o modo agente (ferramentas). Os termos terminam
# em \w* de propósito: "notícias" tem letras depois de "notíc" e uma âncora
# \b logo ali dentro NUNCA casava — por isso pedidos de notícias caíam no
# modo comum (sem ferramenta nenhuma) e a IA dizia que não conseguia.
_AGENT_TRIGGER = re.compile(
    r"(?i)\b(apk|android|gradle\w*|compil\w*|instal\w*|execut\w*|rodar|rode|rodando|"
    r"terminal|shell|console|comando|depend[eê]ncias?|pip3?\s+install|npm|yarn|"
    r"git\s+(clone|pull|push|commit|checkout|status|diff|merge)|docker|"
    r"sdkmanager|adb|kotlin|pytest|javac|java\s+-|cmake|make\b|build|"
    r"python3?\s+(-m|\S+\.py)|node\s+(-|server\b|index\b|\S+\.(js|ts))|"
    r"servidor|localhost|vite|porta|subir|suba|sobe|"
    r"que\s+horas|horas?\s+(agora|atuais?|s[ãa]o)|"
    r"hor[áa]rio\s+(agora|atual|de\s+bras[íi]lia|em\s+\w+)|"
    r"clima|chuva|chover|chova|previs\w*|"
    r"not[ií]c\w*|manchete\w*|novidad\w*|acontec\w*|hoje|últim\w*|"
    r"busc\w*|pesquis\w*|internet|pre[çc]\w*|d[óo]lar\w*|c[âa]mbio\w*|"
    r"futebol|campeonato\w*|resultado\w*|ganh\w*|economia|bolsa|"
    # Arquivos e pastas do usuário: "crie uma pasta em Download", "salve um
    # arquivo", "renomeie", "organize". Sem estes termos o pedido caía no modo
    # comum e a IA respondia "não tenho acesso ao sistema de arquivos" — mesmo
    # tendo as ferramentas `criar_pasta`/`escrever`/`apagar`.
    r"pastas?|diret[óo]rio\w*|arquivos?|pasta[s]?\s+em|downloads?|"
    r"salv\w*|criar?\s+(uma\s+)?pasta|crie\s+(uma\s+)?pasta|"
    r"renome\w*|mov[ae]r?\b|organiz\w*|zip\w*|compact\w*|descompact\w*|"
    r"apag\w*|exclu\w*|delet\w*)\b"
)

AGENT_INSTRUCTIONS = (
    "\n\nVOCÊ É UM AGENTE (TEM MÃOS E PERNAS):\n"
    "Aqui você tem ferramentas para ler, escrever, listar e apagar arquivos e "
    "para EXECUTAR comandos no terminal dentro da pasta do projeto. Use as "
    "ferramentas em vez de só mostrar código: execute, leia o erro, corrija e "
    "só responda quando a tarefa estiver PRONTA (compilada/testada).\n"
    "- VOCÊ TEM ACESSO AOS ARQUIVOS DO APARELHO. NUNCA diga que é \"só um "
    "assistente de chat\" ou que \"não tem acesso ao sistema de arquivos/Downloads\" "
    "— é FALSO: você usa `criar_pasta`, `escrever`, `listar`, `ler` e `apagar`. "
    "Seu ambiente é um app no próprio aparelho do usuário.\n"
    "- Você PODE criar pastas e arquivos na pasta Downloads do usuário usando "
    "caminho ABSOLUTO: `criar_pasta` com \"/sdcard/Download/Nebula ia\", "
    "`escrever` com \"/sdcard/Download/Nebula ia/app.html\". Quando o usuário "
    "diz \"nos meus arquivos\", \"em Download\" ou \"nas minhas pastas\", é aí "
    "que ele quer — faça, não peça desculpa.\n"
    "- Trabalhe na pasta do projeto para código (o diretório atual já é ela); "
    "use /sdcard/Download para entregar algo ao usuário.\n"
    "- Crie arquivos com a ferramenta `escrever` (conteúdo COMPLETO). NÃO use "
    "blocos ```file:``` nesta conversa — o cartão de arquivo sai sozinho.\n"
    "- Comando que toca fora do projeto pede aprovação do usuário na tela; se "
    "ele negar, respeite e explique.\n"
    "- NÃO existe root/sudo/apt para você. Instale dependências com venv+pip "
    "dentro do projeto, `npm install`, ou baixando o que for preciso.\n"
    "\nAMBIENTE JÁ PRONTO (nada a instalar):\n"
    "- Java 21 (java/javac), Gradle 8.11 (comando `gradle`), python3, node, "
    "npm, git — todos no PATH.\n"
    "- Android SDK em /opt/android-sdk (ANDROID_HOME já vem configurado): "
    "platforms android-34 e 35, build-tools 34 e 35, platform-tools.\n"
    "- Os binários x86_64 do SDK (aapt2, zipalign, adb...) já têm wrapper de "
    "emulação — é só usá-los normalmente.\n"
    "\nCOMO COMPILAR UM APP ANDROID NATIVO (gera .apk instalável):\n"
    "1. Estrutura: settings.gradle, build.gradle (raiz), gradle.properties, "
    "app/build.gradle, app/src/main/AndroidManifest.xml e as Activities.\n"
    "2. Em gradle.properties OBRIGATORIAMENTE:\n"
    "   org.gradle.jvmargs=-Xmx1536m -Dfile.encoding=UTF-8\n"
    "   android.useAndroidX=true\n"
    "   android.aapt2FromMavenOverride=/opt/android-sdk/wrappers/aapt2\n"
    "3. Compile com: gradle assembleDebug --no-daemon --stacktrace\n"
    "   (a primeira vez baixa dependências e pode demorar alguns minutos)\n"
    "4. O APK sai em app/build/outputs/apk/debug/app-debug.apk — o sistema "
    "detecta e copia sozinho pra /sdcard/Download/<projeto>.apk (é esse "
    "arquivo que o usuário instala; não precisa copiar na mão).\n"
    "- Versões seguras: AGP 8.7.3, Gradle 8.11.1, compileSdk 35, minSdk 24, "
    "sourceCompatibility Java 17.\n"
    "- Erro de aapt2/arquitetura = confira o android.aapt2FromMavenOverride "
    "acima e rode de novo.\n"
    "- Para apps web/mobile com npm: `npm create vite@latest` também funciona.\n"
    "\nTEMPO REAL — você NÃO sabe o que aconteceu depois do seu treinamento:\n"
    "- `clima`: tempo agora + previsão de qualquer cidade.\n"
    "- `hora`: data/hora atuais de qualquer fuso (padrão: Brasília).\n"
    "- `noticias`: manchetes do dia ou de um assunto qualquer.\n"
    "- `buscar`: procura na web (preços, versões, o que está acontecendo).\n"
    "- `imagens`: fotos reais e livres (Openverse + Wikimedia) para um tema. "
    "O tema deve ser um SUBSTANTIVO CONCRETO de coisa fotografável (\"leão\", "
    "\"pizza\", \"marte\") — NUNCA adjetivo/marketing (\"incrível\", \"profissional\") "
    "nem categoria vazia (\"animais\", \"coisas\"). Use ao criar site/página e "
    "coloque SOMENTE as URLs devolvidas em <img>, com alt em português, "
    "`object-cover` e cantos arredondados. Nunca invente link de imagem.\n"
    "- `guia`: biblioteca de 300+ agentes especialistas (design, marca, copy, "
    "SEO, engenharia, marketing). Consulte ANTES de criar site/app/página para "
    "puxar o padrão de agência: acao=buscar acha os agentes do assunto, "
    "acao=ler abre um pelo caminho, acao=listar mostra as áreas.\n"
    "- Para clima, hora, notícias, preços, campeonatos, lançamentos e fatos "
    "atuais SEMPRE chame a ferramenta certa antes de responder — nunca "
    "adivinhe número, data ou manchete de cabeça.\n"
    "\nFLUXO DE TESTE — mostrar ANTES de compilar:\n"
    "- Site/app web: suba um servidor de teste com a ferramenta `servidor` "
    "(acao=iniciar; comando tipo `npm run dev` ou `python3 -m http.server 8000`), "
    "passe a URL pro usuário abrir no navegador e, a cada ajuste que ele pedir, "
    "refaça o código com o servidor no ar (acao=status confirma).\n"
    "- SÓ rode o build final (`npm run build` / `gradle assembleDebug`) quando o "
    "usuário disser que está pronto. Termine pedindo acao=parar.\n"
    "- Android nativo não tem preview no navegador: ajuste os arquivos à vontade "
    "e compile só quando ele pedir (o 2º build é incremental, rápido).\n"
    "- NUNCA compile \"de teste\"/no meio do desenvolvimento: rode o build "
    "APENAS quando o usuário pedir o app final — um único APK por pedido, "
    "sem gerar APKs desnecessários (cada build deixa lixo e confunde quem "
    "vai instalar).\n"
    "\nAo final, responda em português: o que foi feito, como ficou, como usar."
)

app = FastAPI(title="Nébula API", version="0.2.0")

# CORS: localhost (uso no aparelho) + o que vier em CORS_ORIGINS (no deploy).
_cors_extra = [
    origem.strip()
    for origem in os.getenv("CORS_ORIGINS", "").split(",")
    if origem.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"] + _cors_extra,
    allow_origin_regex=os.getenv("CORS_ORIGIN_REGEX", r".*") or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _definir_sala(request: Request, call_next):
    """Guarda a "sala" da pessoa (o apelido) para este pedido.

    O site manda o apelido no cabeçalho X-Nebula-Sala; cada pedido enxerga
    só os dados daquela sala. Sem o cabeçalho, cai em "local".
    """
    db.definir_sala(_sala(request.headers.get("x-nebula-sala")))
    return await call_next(request)


db.init_db()

# Arquivos gerados pela IA: /files/<projeto>/<arquivo>
app.mount(
    "/files",
    StaticFiles(directory=str(workspace.workspace_dir())),
    name="files",
)

_api_key = os.getenv("GEMINI_API_KEY", "").strip()
if _api_key.lower() in PLACEHOLDER_KEYS:
    _api_key = ""

# Keys extras (contas Google diferentes): cada key tem cota própria de
# IMAGEM (Nano Banana), então rotação de 2-3 keys multiplica o que sai/dia.
_extra_keys = [
    key.strip()
    for key in os.getenv("GEMINI_API_KEYS", "").split(",")
    if key.strip() and key.strip().lower() not in PLACEHOLDER_KEYS
]
_gemini_keys = [_api_key] if _api_key else []
_gemini_keys += [key for key in _extra_keys if key not in _gemini_keys]

gemini: GeminiClient | None = None
if _gemini_keys:
    gemini = GeminiClient(
        api_key=_gemini_keys[0],
        extra_api_keys=_gemini_keys[1:],
        models=GEMINI_MODELS,
        embedding_model=EMBEDDING_MODEL,
        memory_models=MEMORY_MODELS,
        image_models=IMAGE_MODELS,
    )

    # Em segundo plano, descobre qual modelo está respondendo agora e guarda
    # o resultado: a primeira mensagem do usuário já começa no modelo certo
    # em vez de percorrer a lista de reservas (antes ia até 20 s só de fila).
    threading.Thread(
        target=gemini.warmup, daemon=True, name="nebula-teste-modelos"
    ).start()


# ---------------------------------------------------- chave por usuário
# A Nébula pode rodar de graça: quem acessa cola a PRÓPRIA chave do Google
# (Gemini) numa tela na primeira vez, e o app manda essa chave no cabeçalho
# `X-Gemini-Key`. Assim o custo é de cada um e nenhuma chave fica no código.
#
# O `.env` do dono do host continua valendo como reserva: se a pessoa não
# trouxer chave, usa a do host (é o que permite você mesmo usar sem colar nada).
_USER_CLIENTS: dict[str, "GeminiClient"] = {}
_USER_CLIENTS_LOCK = threading.Lock()
MAX_USER_CLIENTS = 50  # teto de memória: 50 chaves distintas em uso

# Cabeçalhos aceitos (o frontend manda o primeiro; os outros são compatibilidade).
_CHAVE_HEADERS = ("x-gemini-key", "x-api-key", "authorization")


def _chave_do_pedido(request) -> str:
    """Lê a chave do usuário do cabeçalho; devolve "" se não houver."""
    if request is None:
        return ""
    for nome in _CHAVE_HEADERS:
        valor = request.headers.get(nome, "").strip()
        if valor:
            if valor.lower().startswith("bearer "):
                valor = valor[7:].strip()
            # Chaves do Gemini/Google começam com "AIza" (formato novo) ou
            # "AQ." (formato antigo, tipo OAuth). Um filtro leve evita que
            # qualquer lixo vire tentativa de conexão.
            if len(valor) >= 20 and valor not in PLACEHOLDER_KEYS:
                return valor
    return ""


def _client_para(chave: str) -> "GeminiClient | None":
    """Cliente do Gemini APENAS pela chave enviada pelo usuário.

    A ideia aqui é simples: CADA UM usa a PRÓPRIA chave do Google AI Studio.
    Se não vier chave no cabeçalho X-Gemini-Key, devolve None e o app bloqueia
    na tela pedindo a chave. Nunca usa a chave do .env para outros acessarem."""
    if not chave:
        return None
    with _USER_CLIENTS_LOCK:
        pronta = _USER_CLIENTS.get(chave)
    if pronta is not None:
        return pronta
    try:
        cliente = GeminiClient(
            api_key=chave,
            models=GEMINI_MODELS,
            embedding_model=EMBEDDING_MODEL,
            memory_models=MEMORY_MODELS,
            image_models=IMAGE_MODELS,
        )
    except Exception:  # noqa: BLE001 - chave inválida não derruba a rota
        return None
    with _USER_CLIENTS_LOCK:
        if len(_USER_CLIENTS) >= MAX_USER_CLIENTS and chave not in _USER_CLIENTS:
            # Descarta a mais antiga para não crescer sem limite.
            _USER_CLIENTS.pop(next(iter(_USER_CLIENTS)), None)
        _USER_CLIENTS[chave] = cliente
    try:
        threading.Thread(target=cliente.warmup, daemon=True).start()
    except Exception:  # noqa: BLE001
        pass
    return cliente


class Attachment(BaseModel):
    """Imagem/arquivo que o usuário manda junto com a mensagem.

    `data` é o conteúdo em base64 (sem o prefixo "data:...;base64,"). Trafega
    dentro do JSON porque o endpoint é o mesmo do texto — evita um segundo
    caminho de upload e funciona igual no celular.
    """

    name: str = Field(max_length=200)
    mime_type: str = Field(max_length=120)
    data: str


# Limites generosos, mas que ainda cabem num pedido só do Gemini.
MAX_ATTACHMENTS = 4
MAX_ATTACHMENT_CHARS = 12_000_000  # ~9 MB em base64


class ChatRequest(BaseModel):
    message: str = Field(default="", max_length=32000)
    conversation_id: int | None = None
    use_memory: bool = True
    # Quem responde: "auto" ou "gemini" (só o Google).
    provider: str = "auto"
    # Imagens/arquivos que vão junto com a mensagem (até MAX_ATTACHMENTS).
    attachments: list[Attachment] = []
    # Modo off: o site gerado não pode depender de internet (sem CDN nenhum).
    offline: bool = False
    # Personalidade (vem do painel de Ajustes do app; vazio = padrão).
    ai_name: str = Field(default="", max_length=40)
    user_name: str = Field(default="", max_length=40)
    tone: str = Field(default="", max_length=20)  # direto | detalhado
    reply_size: str = Field(default="", max_length=20)  # curto | longo
    # Pedido direto de imagem (botão "+" → "Gerar imagem"); a heurística
    # continua valendo para quem só digita "desenhe um gato".
    image: bool = False
    # Gerar de novo a resposta da última pergunta (sem repetir a pergunta).
    regenerate: bool = False
    # Editar aquela mensagem do usuário e gerar de novo a partir dela.
    edit_message_id: int | None = None


class RenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class ApprovalDecision(BaseModel):
    """Resposta do usuário ao cartão " Permitir/Negar" de um comando."""

    id: str = Field(max_length=64)
    approved: bool


class ChatResponse(BaseModel):
    conversation_id: int
    reply: str
    model: str | None = None
    project: str | None = None
    files: list[dict] = []


def _cliente_da_requisicao(request: Request) -> "GeminiClient | None":
    """Cliente Gemini pelo header X-Gemini-Key. Sem chave = None (exige chave do usuário)."""
    chave = _chave_do_pedido(request)
    return _client_para(chave)


def _require_provider() -> None:
    """Garante que existe pelo menos um jeito de responder."""
    if gemini is None:
        raise HTTPException(
            status_code=503,
            detail="Cole sua chave da API do Google Gemini (https://aistudio.google.com/apikey). Cada pessoa precisa usar a própria chave.",
        )


def _reply_pieces(
    instruction: str,
    history: list[dict],
    message: str,
    on_model,
    attachments: list[dict] | None = None,
    thinking_budget: int = 0,
    search: bool = False,
    on_sources=None,
    cliente: "GeminiClient | None" = None,
) -> Iterator[str]:
    """Gera a resposta com o Gemini.

    O cliente do Gemini já tenta os modelos de reserva dele quando a cota de um
    acaba. Depois que já mostramos algo na tela, um erro é repassado em vez de
    recomeçar, para não duplicar a resposta.

    `search` liga a busca na web (as fontes chegam em `on_sources`).
    """
    g = cliente or gemini
    if g is None:
        raise RuntimeError("GEMINI_API_KEY não configurada.")
    for piece in g.stream(
        instruction,
        history,
        message,
        on_model=on_model,
        attachments=attachments,
        thinking_budget=thinking_budget,
        search=search,
        on_sources=on_sources,
    ):
        yield piece


def _attach_dicts(attachments: list[Attachment]) -> list[dict]:
    """Modelos -> dicionários simples (é assim que os anexos vão para o banco)."""
    return [
        {"name": item.name, "mime_type": item.mime_type, "data": item.data}
        for item in attachments
    ]


def _check_attachments(attachments: list[Attachment]) -> None:
    if len(attachments) > MAX_ATTACHMENTS:
        raise HTTPException(
            status_code=413,
            detail=f"Máximo de {MAX_ATTACHMENTS} anexos por mensagem.",
        )
    for item in attachments:
        if len(item.data) > MAX_ATTACHMENT_CHARS:
            raise HTTPException(
                status_code=413,
                detail=f"O anexo \"{item.name}\" é grande demais (limite ~9 MB).",
            )


def _gemini_attachments(attachments: list[dict]) -> list[dict]:
    """Decodifica o base64 para bytes, que é o que a API do Gemini espera."""
    out: list[dict] = []
    for item in attachments:
        try:
            raw = base64.b64decode(item["data"], validate=True)
        except Exception:  # noqa: BLE001 - anexo inválido é ignorado
            continue
        out.append({"mime_type": item["mime_type"], "data": raw})
    return out


_TRIVIAL_REPLIES = {
    "oi": "Oi! No que posso te ajudar hoje?",
    "ola": "Olá! No que posso te ajudar hoje?",
    "olá": "Olá! No que posso te ajudar hoje?",
    "hi": "Hi! How can I help you today?",
    "hey": "Hey! What can I help you with?",
    "hello": "Olá! How can I help you today?",
    "bom dia": "Bom dia! No que posso te ajudar hoje?",
    "boa tarde": "Boa tarde! No que posso te ajudar hoje?",
    "boa noite": "Boa noite! No que posso te ajudar hoje?",
    "tudo bem": "Tudo ótimo por aqui! E você, como vai?",
    "como vai": "Vou muito bem! E você, como tá?",
    "e aí": "E aí! No que posso te ajudar hoje?",
    "e ai": "E aí! No que posso te ajudar hoje?",
    "obrigado": "De nada! Fico feliz em ajudar.",
    "obrigada": "De nada! Fico feliz em ajudar.",
    "valeu": "Valeu! Se precisar de algo é só chamar.",
    "tchau": "Tchau! Até mais!",
    "até mais": "Até mais! Cuide-se bem!",
    "ate mais": "Até mais! Cuide-se bem!",
}


def _trivial_reply(message: str, attachments: list) -> str | None:
    """Resposta pronta para cumprimentos/piadinhas de saudação.

    Só vale quando NÃO há anexo e o texto é exatamente uma das frases curtas
    (após tirar pontuação e caixa). Assim "oi, me explique relatividade"
    continua indo para o Gemini — só "oi" puro cai no atalho instantâneo.
    """
    if attachments:
        return None
    text = message.strip().lower().strip(".!?,;:…")
    return _TRIVIAL_REPLIES.get(text)
_TITLE_FILLERS = (
    "por favor",
    "me explique",
    "me explica",
    "explique",
    "explica",
    "você pode",
    "voce pode",
    "pode me",
    "gostaria que",
    "queria que",
    "preciso que",
    "como faço para",
    "como faco para",
    "como faço",
    "como faco",
    "por gentileza",
)


def _limpar_titulo(texto: str) -> str:
    """Tira enchimento do começo e corta na palavra (sem cortar no meio)."""
    t = texto.strip().strip("\"'“”").strip()
    baixo = t.lower()
    mudou = True
    while mudou and t:
        mudou = False
        for ench in _TITLE_FILLERS:
            if baixo.startswith(ench):
                t = t[len(ench) :].lstrip(" ,;:.!?—-")
                baixo = t.lower()
                mudou = True
    t = t.rstrip(".,;:!?()[]{}").strip()
    if len(t) <= 55:
        return t
    corte = t[:55].rsplit(" ", 1)[0]
    return (corte or t[:55]).rstrip(" ,;:.-") + "…"


def _title_for(message: str, attachments: list[Attachment]) -> str:
    """Título da conversa nova (mais inteligente).

    Pega o assunto principal do texto (tirando o enchimento inicial), corta na
    palavra; se não houver texto, usa o nome do anexo.
    """
    text = message.strip()
    if text:
        # Primeira frase costuma resumir o assunto melhor que o texto todo.
        primeira = text.split("\n", 1)[0]
        for fim in (". ", "? ", "! "):
            if fim in primeira:
                primeira = primeira.split(fim, 1)[0] + fim.strip()
                break
        titulo = _limpar_titulo(primeira)
        if titulo:
            return titulo[:70]
        return _limpar_titulo(text)[:70] or "Nova conversa"
    if attachments:
        return f"📎 {attachments[0].name[:70]}"
    return "Nova conversa"


def _resolve_turn(
    req: ChatRequest,
) -> tuple[int, list[dict], bool, str, list[dict], bool]:
    """Resolve a conversa e a mensagem deste turno.

    Devolve (conversation_id, histórico, criada_agora, mensagem, anexos, já_salva).

    - normal: histórico = tudo que já existe; a mensagem é salva depois.
    - regenerate: reaproveita a última mensagem do usuário e apaga o que veio
      depois dela (a resposta antiga), para gerar outra.
    - edit_message_id: troca o texto daquela mensagem, apaga o que veio depois
      e gera de novo. Nos dois últimos casos a mensagem já está no banco.
    """
    if req.conversation_id is None:
        conversation_id = db.create_conversation(
            title=_title_for(req.message, req.attachments)
        )
        return (
            conversation_id,
            [],
            True,
            req.message.strip(),
            _attach_dicts(req.attachments),
            False,
        )

    if not db.conversation_exists(req.conversation_id):
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")

    conversation_id = req.conversation_id
    messages = _clean_history(db.get_messages(conversation_id))

    if req.edit_message_id is not None:
        alvo = db.get_message(req.edit_message_id)
        if (
            alvo is None
            or alvo["conversation_id"] != conversation_id
            or alvo["role"] != "user"
        ):
            raise HTTPException(status_code=404, detail="Mensagem não encontrada.")

        novos = _attach_dicts(req.attachments) or alvo["attachments"]
        texto = req.message.strip() or alvo["content"]
        db.update_message(alvo["id"], texto, novos)
        db.delete_messages_after(conversation_id, alvo["id"])
        history = [m for m in messages if m["id"] < alvo["id"]]
        return conversation_id, history, False, texto, novos, True

    if req.regenerate:
        ultima = next(
            (m for m in reversed(messages) if m["role"] == "user"), None
        )
        if ultima is None:
            raise HTTPException(status_code=400, detail="Nada para gerar de novo.")
        db.delete_messages_after(conversation_id, ultima["id"])
        history = [m for m in messages if m["id"] < ultima["id"]]
        return (
            conversation_id,
            history,
            False,
            ultima["content"],
            ultima["attachments"],
            True,
        )

    return (
        conversation_id,
        messages,
        False,
        req.message.strip(),
        _attach_dicts(req.attachments),
        False,
    )


# ---------------------------------------------------------------- memória


def _memory_block(message: str, use_memory: bool) -> str:
    """Trecho com o que a Nébula já sabe do usuário (ou string vazia)."""
    if not (use_memory and gemini is not None):
        return ""
    msg = message.strip()
    if not msg:
        # Mensagem só com anexo: não há o que buscar na memória.
        return ""
    # Mensagem trivial (saudação pura) não precisa de memória — e não paga
    # o custo de uma ida à API de embeddings.
    if _TRIVIAL_REPLIES.get(msg.lower().strip(".!?,;:…")) is not None:
        return ""

    # Poucos fatos guardados = cola todos direto e pula a ida de ~600 ms à
    # API de embeddings (que era feita ANTES de cada resposta começar).
    # A busca por similaridade só entra quando a memória já é grande.
    try:
        guardadas = db.all_memories()
    except Exception:  # noqa: BLE001 - memória é opcional, nunca quebra
        guardadas = []
    if guardadas and len(guardadas) <= 8:
        facts = "\n".join(f"- {row['content']}" for row in guardadas[:8])
        return MEMORY_HEADER + facts + MEMORY_FOOTER

    try:
        found = memory.search(gemini.embed(msg, task_type="RETRIEVAL_QUERY"))
    except Exception:  # noqa: BLE001 - memória é opcional, nunca quebra a resposta
        return ""

    if not found:
        return ""

    facts = "\n".join(f"- {item['content']}" for item in found)
    return MEMORY_HEADER + facts + MEMORY_FOOTER


# Palavras que denunciam um pedido de site/código (falso positivo é inofensivo:
# as regras de design começam com "ao criar site…", então só servem se houver site).
_BUILD_KEYWORDS = (
    "site", "página", "pagina", "page", "web", "html", "css", "javascript",
    "app", "aplicativo", "portfólio", "portfolio", "loja", "landing", "blog",
    "dashboard", "formulário", "formulario", "template", "design", "clone",
    "jogo", "script", "código", "codigo", "arquivo", "frontend", "interface",
    "layout", "responsivo", "hero", "calculadora", "conversor", "quiz",
    "pomodoro", "relógio", "relogio", "python", "react", "slide", "apresentação",
    "apresentacao", "tema",
)

# Ajuste numa página que já existe: "adicione ilustrações dos produtos",
# "troque as fotos", "coloque imagens no cardápio", "quero fotos de verdade".
# Sem isso o pedido caía na conversa comum (sem thinking, sem regras de design
# e SEM busca de fotos) e a IA respondia que "não conseguia buscar imagens" —
# mesmo tendo a ferramenta.
_AJUSTE_SITE = re.compile(
    r"(?i)\b(adicion\w*|acrescent\w*|inclu\w*|insir\w*|p[õo]e|por|coloc\w*|"
    r"coloqu\w*|troc\w*|substitu\w*|atualiz\w*|melhor\w*|aument\w*|"
    r"ilustra\w*|imagens?|fotos?|figuras?|fotografias?|imagem|"
    r"reais?|verdadeir\w*|de verdade)\b"
)
# O que a página tem (o alvo do ajuste).
_AJUSTE_ALVO = re.compile(
    r"(?i)\b(produtos?|card[áa]pio|menu|se[çc][õo]es?|p[áa]gina|site|banner|"
    r"hero|cabe[çc]alho|rodap[ée]|galeria|servi[çc]os?|planos?|depoimentos?|"
    r"equipe|time|sobre|contato|destaques?|itens?|pratos?|lanches?)\b"
)


def _contexto_do_pedido(history: list[dict]) -> str:
    """Tema da conversa — dá assunto a um ajuste curto.

    "agora adicione ilustrações dos produtos" sozinho não diz de que site é.
    O tema está na PRIMEIRA fala com cara de pedido de site ("crie um site
    para uma pizzaria…"); as últimas mensagens costumam ser só ajustes
    ("não mudou nada", "só gerar uma imagem") e poluem a busca de fotos.
    """
    falas = [
        str(m.get("content") or "").replace("\n", " ")
        for m in history
        if m.get("role") == "user"
    ]
    if not falas:
        return ""
    for fala in falas:
        if _SITE_REQUEST.search(fala):
            return fala[:300]
    return " ".join(falas[-2:])[:300]


def _ajuste_de_site(message: str) -> bool:
    """Pedido de mudança numa página que a IA já criou nesta conversa.

    Vale com alvo explícito ("imagens nos produtos") OU só com o pedido de
    mídia ("imagens reais", "quero fotos de verdade") — aí o alvo é a página
    toda e o assunto vem do histórico da conversa.
    """
    text = message.strip()
    if not text or len(text) > 400:
        return False
    if not _AJUSTE_SITE.search(text):
        return False
    if _AJUSTE_ALVO.search(text):
        return True
    # Pedido de mídia sem alvo: precisa MESMO pedir foto/imagem. "reais" sozinho
    # ("os dados são reais?") não cria página nenhuma.
    return bool(
        re.search(r"(?i)\b(imagens?|fotos?|figuras?|fotografias?|ilustra\w*)\b", text)
    )


def _looks_like_build(message: str) -> bool:
    """True quando o pedido envolve site/código/arquivo.

    É o gatilho para as duas coisas pesadas (que custam qualidade ou
    velocidade): as regras de design no prompt e o thinking do Gemini.
    Mensagem longa também conta — pedido grande pede raciocínio.
    """
    text = message.strip().lower()
    if len(text) > 500:
        return True
    if any(word in text for word in _BUILD_KEYWORDS):
        return True
    return _ajuste_de_site(message)


def _thinking_budget(message: str) -> int:
    """0 para conversa comum (rápido), budget para pedidos de site/código."""
    return THINKING_BUDGET_BUILD if _looks_like_build(message) else 0


# Pedido de site/página: só aí vale buscar fotos reais do tema antes de gerar.
# "css" sozinho não conta — pergunta sobre linguagem não cria arquivo nenhum.
_SITE_REQUEST = re.compile(
    r"(?i)\b(site|sites|p[áa]gina|p[áa]ginas|landing|website|web|page|"
    r"portf[óo]lio|blog|loja|card[áa]pio|one[- ]page)\b"
)
# Palavras de comando que não ajudam a achar foto nenhuma.
_TEMA_STOP = re.compile(
    r"(?i)\b(crie|criar|cria|fa[çc]a|fazer|mont[ae]|montar|desenvolv[ae]|"
    r"um|uma|uns|umas|o|a|os|as|de|do|da|dos|das|para|pra|com|sem|sobre|"
    r"que|e|em|no|na|meu|minha|nosso|nossa|quero|gostaria|preciso|"
    r"site|sites|p[áa]gina|p[áa]ginas|landing|page|web|website|html|css|"
    r"bonit[oa]|modern[oa]|profissional|simples|completo|completa|"
    r"cards?|planos?|pre[çc]os?|fotos?|imagens?|se[çc][õo]es|depoimentos?|"
    r"galeria|layout|contato|servi[çc]os|produtos?|home|hero|menu|"
    r"bairro|card[áa]pio|hor[áa]rios?|agendamento|atua[çc][ãa]o|atua[çc][õo]es|"
    r"[áa]reas?|especialidades?|benef[íi]cios|diferenciais|quem somos|"
    r"index|style|script|js|javascript|typescript|tailwind|react|vue|angular|"
    r"svelte|node|bootstrap|componentes?|responsiv[oa]|mobile|desktop|"
    r"arquivos?|pastas?|projeto|chamad[ao]|"
    r"zool[óo]gico|zoologico|aqu[áa]rio|museu|parque|reserva|card(?:s)?|item|itens|"
    r"cada|animal|animais|texto|curto|sobre|"
    r"site|p[áa]gina|landing|web|website|onepage|"
    r"crie|criar|cria|fa[çc]a|fazer|mont[ae]|montar|desenvolv[ae]|"
    r"por favor|agora|depois|completo|simples|"
    r"um|uma|uns|umas|o|a|os|as|de|do|da|dos|das|para|pra|com|sem|sobre|"
    r"que|e|em|no|na|meu|minha|nosso|nossa|quero|gostaria|preciso)\b"
)


# Palavra depois de "chamada/o" ou um par Capitalizado no meio do pedido quase
# sempre é NOME DE MARCA inventado ("Forja Fitness", "Bella Massa") — não ajuda
# na busca de fotos e piora o resultado (traz logo de anime, letreiro etc.).
_MARCA = re.compile(
    r"(?i)\b(?:chamad[ao]|nome(?:ado)?(?:\s+de)?)\s+([A-ZÀ-Þ][\wÀ-ÿ-]*(?:\s+[A-ZÀ-Þ][\wÀ-ÿ-]*)*)"
)
_MARCA_CAPS = re.compile(r"\b[A-ZÀ-Þ][a-zà-ÿ]{2,}(?:\s+[A-ZÀ-Þ][a-zà-ÿ]{2,})+\b")


def _tema_do_pedido(message: str) -> str:
    """'crie um site de receitas veganas' -> 'receitas veganas' (busca de foto)."""
    # Parênteses/colchetes quase sempre trazem a lista de arquivos e tecnologias
    # ("(index.html + style.css)", "[React]") — isso não é o tema e poluía a
    # busca de fotos (o Wikimedia devolvia nada e o site saía sem imagem).
    texto = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", message or "")
    # Tira o nome de marca (inventado) antes de montar o tema.
    texto = _MARCA.sub(" ", texto)
    texto = re.sub(r"[^\wÀ-ÿ\s-]", " ", texto)
    texto = _TEMA_STOP.sub(" ", texto)
    palavras = [p for p in texto.split() if len(p) > 2]
    # Segunda passada: se sobrou um par Capitalizado, provavelmente é a marca.
    tema = " ".join(palavras[:6])
    tema = _MARCA_CAPS.sub(" ", tema)
    palavras = [p for p in tema.split() if len(p) > 2][:6]
    return " ".join(palavras) or (message or "").strip()[:60]


def _assuntos_do_pedido(texto: str) -> list[str]:
    """Assuntos concretos citados no pedido, para pré-aquecer as fotos.

    "fotos de tamanduá-bandeira, arara-azul e mico-leão-dourado" → esses três.
    Pega só termos com cara de assunto (substantivo), ignorando verbo de
    comando e palavra de ligação. Serve para AQUECER — errar aqui não estraga
    nada, só deixa de economizar tempo.
    """
    if not texto:
        return []
    # Fica com o trecho mais "de lista" do pedido: a última frase costuma ser
    # onde os assuntos são enumerados ("…precisa da foto do animal: X, Y e Z").
    trecho = re.split(r"[.:!?\n]", texto)[-1] or texto
    limpo = re.sub(
        r"(?i)\b(foto|fotos|imagem|imagens|figura|figuras|real|reais|ilustra\w*|"
        r"coloque|colocar|adicione|adicionar|inclua|incluir|troque|substitua|"
        r"atualize|melhore|quero|preciso|faça|fazer|site|página|pagina|"
        r"cada|todos|todas|com|sem|para|sobre|uma|uns|umas|dos|das|que|"
        r"precisa|próprio|proprio|animal|animais|espécie|especie|ficha|"
        r"agora|ent[ãa]o|depois|tamb[ée]m|mais|"
        r"chamad[ao]|chamada|nome|card|cards|seç[ãa]o|secoes|bloco|blocos)\b",
        " ",
        trecho,
    )
    # Listas vêm separadas por vírgula ou por " e ". Cada pedaço que pareça um
    # assunto (1-3 palavras, sem número) vira termo de busca.
    pedacos = re.split(r"\s*(?:,|;|\be\b|\bmais\b)\s*", limpo)
    assuntos: list[str] = []
    for pedaco in pedacos:
        palavras = [
            p for p in re.findall(r"[^\W\d_]+", pedaco, flags=re.UNICODE) if len(p) > 2
        ]
        # Um pedaço com 3+ palavras e sem hífen costuma ser frase solta, não
        # assunto; fica só com as duas últimas (o núcleo do termo).
        if len(palavras) >= 3 and "-" not in pedaco:
            palavras = palavras[-2:]
        termo = " ".join(palavras[:3]).strip()
        if termo and termo.lower() not in assuntos:
            assuntos.append(termo.lower())
    return assuntos[:6]


def _fotos_do_pedido(
    message: str, offline: bool, historico: str = ""
) -> list[dict]:
    """Fotos reais para o tema, só em pedido de site (e nunca no modo off)."""
    if offline or not _looks_like_build(message):
        return []
    # Modo off (sem internet): a página não pode depender de foto remota.
    if re.search(r"(?i)\boffline\b", message or ""):
        return []
    # Pedido direto de site OU ajuste numa página já criada nesta conversa.
    ajuste = _ajuste_de_site(message)
    if not _SITE_REQUEST.search(message or "") and not ajuste:
        return []
    # A conversa manda no tema. Um ajuste ("coloque uma foto em cada item do
    # cardápio") pode até conter "cardápio" — palavra que casa _SITE_REQUEST —
    # mas não diz de QUE site é. Nesses casos o tema tem de vir do pedido
    # original ("site para uma pizzaria"); sem isso a busca saía com o lixo do
    # próprio ajuste ("coloque real diferente cada item…") e voltava pintura
    # do século XVI.
    tema_msg = _tema_do_pedido(message or "")
    busca = message or ""
    if historico and (ajuste or not _SITE_REQUEST.search(busca)):
        busca = f"{historico} {tema_msg}"
    # Qual termo semeia as fotos do prompt:
    # - pedido NOVO de site ("crie um site de astronomia…"): o tema do pedido,
    #   extraído pelo _tema_do_pedido (que já tira marca, verbo e parênteses);
    # - AJUSTE com lista de assuntos ("fotos de tamanduá, arara e onça"): os
    #   assuntos ditos agora — é o que o site realmente mostra, e o histórico
    #   aqui só polui (num site "de ilustrações de animais raros… bem
    #   profissional e didático" o histórico virava o termo "mostra ilustrações
    #   raros sua descrição Bem" e a busca devolvia exposição de museu).
    assuntos = _assuntos_do_pedido(message or "") if ajuste else []
    termo = _tema_do_pedido(assuntos[0]) if assuntos else _tema_do_pedido(busca)
    # Aquece, em segundo plano, os assuntos citados no pedido. O agente vai
    # chamar `imagens` um por um mais tarde; se já estiverem em cache, o site
    # não espera os ~9 s de cache frio da Openverse por termo. Aqui vale a
    # lista do pedido inteiro (não só do ajuste): "Lua, Marte, Júpiter e
    # Saturno" aquece os quatro, mesmo num pedido novo de site.
    try:
        realtime.prefetch(_assuntos_do_pedido(message or "") or assuntos or [termo])
    except Exception as exc:  # noqa: BLE001 - pré-aquecimento é bônus
        print(f"[fotos] prefetch não deu: {exc}")
    try:
        fotos = realtime.fotos(termo, 8)
    except Exception as exc:  # noqa: BLE001 - foto é bônus, o site sai sem ela
        print(f"[fotos] não deu para buscar: {exc}")
        return []
    if fotos:
        print(f"[fotos] {len(fotos)} fotos para «{fotos[0]['titulo'][:50]}»")
    else:
        print("[fotos] nenhuma foto para o tema; site sai com SVG/CSS")
    return fotos


# Personalidade (painel de Ajustes): valor vazio = resposta padrão.
TONE_RULES = {
    "direto": "Vá direto ao ponto: sem preâmbulo, sem repetir a pergunta, sem enrolação.",
    "detalhado": (
        "Responda com profundidade: explique o porquê, use exemplos "
        "e estruture quando ajudar."
    ),
}
SIZE_RULES = {
    "curto": "Seja conciso: no máximo 1 a 3 frases, a menos que peçam mais.",
    "longo": (
        "Pode ir mais longe: respostas completas, com passos "
        "e exemplos quando útil."
    ),
}

# Pedidos curtos de imagem: "desenhe um gato", "gere uma foto de praia"...
# (o plural do regex antigo era "imagens?" = "imagen"+s, então a palavra
# "imagem" — a mais usada! — não casava: o pedido caía no modelo, que
# inventava um link de imagem quebrado.)
_IMAGE_NOUN = re.compile(
    r"\b(imagem|imagens|foto|fotos|desenho|desenhos|pintura|quadro|arte|"
    r"ilustra[çc][ãa]o|ilustra[çc][õo]es|meme|wallpaper)\b"
)
_IMAGE_VERB = re.compile(
    r"\b(gere|gerar|gera|crie|criar|cria|fa[çc]a|fazer|faz|desenhe|desenhar|"
    r"desenha|quero|queria|mande|manda|envie|envia|pinte|pintar|mostre|mostra)\b"
)


def _style_block(req: ChatRequest) -> str:
    """Personalidade escolhida no painel de Ajustes (sem nada = padrão)."""
    bullets: list[str] = []
    ai_name = req.ai_name.strip()[:40]
    user_name = req.user_name.strip()[:40]
    if ai_name:
        bullets.append(f"Seu nome é {ai_name}; apresente-se assim se perguntarem.")
    if user_name:
        bullets.append(
            f"O usuário se chama {user_name}; use o nome quando for natural."
        )
    if req.tone in TONE_RULES:
        bullets.append(TONE_RULES[req.tone])
    if req.reply_size in SIZE_RULES:
        bullets.append(SIZE_RULES[req.reply_size])
    if not bullets:
        return ""
    return "\n\nPERSONALIDADE:\n" + "".join(f"- {line}\n" for line in bullets)


def _looks_like_image(message: str) -> bool:
    """True para pedidos curtos de imagem — nunca para pedidos de site."""
    text = message.strip()
    if len(text) > 400 or _looks_like_build(text):
        return False
    low = text.lower()
    if _IMAGE_NOUN.search(low) and _IMAGE_VERB.search(low):
        return True
    # Verbo que só pode significar desenho: "desenhe um gato", "pinte uma cena".
    return bool(re.search(r"\b(desenhe|desenhar|desenha|pinte|pintar)\b", low))


_RICH_SUFFIX = ", cinematic lighting, highly detailed, sharp focus, best quality"

# Links de imagem que a própria Nébula escreve. Se o arquivo não existir, o
# link é falso: o modelo às vezes imita o formato das respostas anteriores e
# inventa um nome — e o chat mostra uma caixinha quebrada em vez da foto.
_IMAGE_LINK = re.compile(r"!\[[^\]]*\]\(\s*(/files/[^)\s]+)\s*\)")

_IMAGE_FAIL_REPLY = (
    "Não consegui gerar a imagem agora — os geradores grátis bateram no limite "
    "neste instante. Espera uns 20 segundos e me pede de novo, que costuma "
    "passar. 🙏"
)


def _files_path(url: str) -> Path | None:
    """Caminho real por trás de um /files/<projeto>/<arquivo>.

    None quando o caminho tentaria sair da pasta dos projetos.
    """
    root = workspace.workspace_dir().resolve()
    try:
        target = (root / unquote(url[len("/files/") :])).resolve()
    except Exception:  # noqa: BLE001 - URL malformada é link falso
        return None
    if target != root and root not in target.parents:
        return None
    return target


def _drop_fake_images(text: str) -> str:
    """Troca link de imagem que não existe por um aviso honesto.

    Serve para o histórico: o modelo copia o formato que vê na conversa, então
    um link quebrado antigo virava vários links quebrados novos.
    """

    def _sub(match: re.Match[str]) -> str:
        target = _files_path(match.group(1))
        if target is not None and target.is_file():
            return match.group(0)
        return "_(imagem não gerada)_"

    return _IMAGE_LINK.sub(_sub, text)


def _clean_history(messages: list[dict]) -> list[dict]:
    """Histórico sem links de imagem quebrados (o modelo tende a imitá-los)."""
    for item in messages:
        if item.get("role") != "user":
            item["content"] = _drop_fake_images(item.get("content") or "")
    return messages


def _rich_prompt(prompt: str) -> str:
    """Prompt em inglês e detalhado: melhora MUITO a qualidade da imagem.

    O Gemini reescreve o pedido com estilo/iluminação/enquadramento; se os
    modelos de texto estiverem fora, seguimos com o pedido original + um
    enfeite em inglês (modelos de imagem rendem mais em inglês).
    """
    if gemini is not None:
        try:
            rich = gemini.enhance_image_prompt(prompt)
            if rich:
                print(f"[imagem] prompt enriquecido: {rich[:90]}…")
                return rich
        except Exception:
            pass
    return prompt + _RICH_SUFFIX


def _try_image(conversation_id: int, prompt: str) -> str | None:
    """Gera a imagem e devolve a URL; None = nada deu certo (segue em texto).

    Ordem dos provedores:
      1. Nano Banana (modelos de imagem do Gemini) — a melhor qualidade;
         rota as keys do Google configuradas (a cota de imagem é por key);
      2. Cloudflare FLUX — volume premium, se houver token no .env;
      3. Pollinations — SEM CHAVE, funciona em qualquer instalação nova;
      4. desiste e o chat responde em texto (nunca trava o usuário).
    """
    prompt = _rich_prompt(prompt)  # enriquecimento vale para todos
    data: bytes | None = None

    if gemini is not None:
        data = gemini.generate_image(prompt)  # Nano Banana; engole erro por key

    if data is None:  # Cloudflare FLUX (premium, se configurado)
        try:
            result = cf_image.generate(prompt)
            if result:
                data, _mime = result
                print("[imagem] cloudflare FLUX: ok")
        except Exception as exc:  # noqa: BLE001 - imagem é bônus, não trava
            print(f"[imagem] cloudflare: {str(exc)[:160]}")

    if data is None:  # sem chave nenhuma: saldo pra qualquer pessoa
        data = pollinations.generate(prompt)  # loga e engole o erro sozinho
        if data is not None:
            print("[imagem] pollinations (sem chave): ok")

    if data is None:
        return None

    try:
        saved = workspace.write_image(_project_for(conversation_id), data)
        return saved["url"]
    except Exception as exc:  # noqa: BLE001 - imagem é bônus, não trava o chat
        print(f"[imagem] falha ao gravar: {exc}")
        return None


# Edição de imagem: "mude a cor pra vermelho", "tire o fundo", "troca o céu
# por noite"... Detecta o pedido e reaproveita a ÚLTIMA imagem da conversa.
_IMAGE_EDIT_VERB = re.compile(
    r"\b(mude|mudar|muda|troque|trocar|troca|edite|editar|edita|altere|alterar|"
    r"altera|refaça|refaz|refaca|deixe|deixar|deixa|torne|tornar|torna|"
    r"remova|remover|remove|adicione|adicionar|adiciona|apague|apagar|apaga|"
    r"melhore|melhorar|melhora|corrija|corrigir|corrige|acrescente|acrescenta|"
    r"coloque|colocar|coloca|pinte|pintar|pinta|deixe a|trocar a|troca a)\b",
    re.IGNORECASE,
)
# Termos que indicam uma mudança visual concreta (cor, fundo, objeto...).
_IMAGE_EDIT_CONTEXT = re.compile(
    r"\b(cor|cores|fundo|céu|ceu|luz|ilumina|estilo|flore|flor|olho|olhos|cabelo|"
    r"roupa|roupas|hat|chapéu|chapeu|óculos|oculos|barba|bigode|fundo|adicion|"
    r"remov|apag|troc|mud|deix|coloc|pint|acrescent|sem |com |para |pra )\b",
    re.IGNORECASE,
)


def _looks_like_image_edit(message: str) -> bool:
    """True quando o pedido é para EDITAR a última imagem (não gerar outra nova)."""
    text = message.strip()
    if not text or len(text) > 400 or _looks_like_build(text):
        return False
    low = text.lower()
    # Só considera edição se tiver verbo de edição E contexto visual.
    return bool(_IMAGE_EDIT_VERB.search(low) and _IMAGE_EDIT_CONTEXT.search(low))


def _last_image_bytes(conversation_id: int) -> tuple[bytes, str] | None:
    """Acha a última imagem gerada na conversa e devolve (bytes, mime).

    Percorre as mensagens de trás pra frente procurando o link
    ![imagem gerada](/files/...). Se o arquivo ainda existir, devolve os
    bytes e o mime. None quando não há imagem editável.
    """
    messages = db.get_messages(conversation_id)
    for msg in reversed(messages):
        if msg.get("role") != "model":
            continue
        match = _IMAGE_LINK.search(msg.get("content") or "")
        if not match:
            continue
        target = _files_path(match.group(1))
        if target is None or not target.is_file():
            continue
        try:
            data = target.read_bytes()
        except Exception:  # noqa: BLE001 - imagem é bônus
            continue
        ext = target.suffix.lower()
        mime = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }.get(ext, "image/jpeg")
        return data, mime
    return None


def _try_image_edit(conversation_id: int, instruction: str) -> bytes | None:
    """Edita a última imagem seguindo o pedido; None = Nano Banana fora.

    Único editor de verdade: o Nano Banana (Gemini) edita mantendo o resto
    da cena. Cloudflare free e Pollinations não têm img2img pra imagem local,
    então não dá pra degradar — se o Nano Banana estiver no limite, devolve
    None e o chamador avisa o usuário (sem chamar o modelo, que inventaria
    um link quebrado).
    """
    found = _last_image_bytes(conversation_id)
    if found is None:
        return None
    image_bytes, mime = found
    prompt = instruction.strip()[:600]

    if gemini is None:
        return None
    try:
        data = gemini.edit_image(image_bytes, mime, prompt)
        if data is not None:
            print("[imagem-edit] nano banana: ok")
            return data
    except Exception as exc:  # noqa: BLE001 - cota/404: não trava
        print(f"[imagem-edit] nano banana: {str(exc)[:160]}")
    return None


def _edit_image_url(conversation_id: int, data: bytes) -> str | None:
    """Grava a imagem editada no workspace e devolve a URL (/files/...)."""
    try:
        saved = workspace.write_image(_project_for(conversation_id), data)
        return saved["url"]
    except Exception as exc:  # noqa: BLE001 - imagem é bônus
        print(f"[imagem-edit] falha ao gravar: {exc}")
        return None


# Respostas honestas de edição (sem chamar o modelo, que inventaria link).
_IMAGE_EDIT_FAIL_REPLY = (
    "Não consegui editar a imagem agora — o editor (Nano Banana) está no "
    "limite neste instante. Espera uns 20 segundos e me pede de novo, que "
    "costuma passar. 🙏"
)
_IMAGE_NO_EDIT_TARGET_REPLY = (
    "Não encontrei nenhuma imagem recente pra editar. Quer que eu gere uma? "
    "Pede tipo: \"gere uma imagem de um gato\"."
)


def _build_instruction(
    message: str,
    use_memory: bool,
    memory_text: str = "",
    offline: bool = False,
    style_block: str = "",
    fotos: list[dict] | None = None,
) -> str:
    """Prompt do Gemini (que devolve os arquivos como blocos de texto).

    `offline` troca o prompt mestre de front-end pela versão modo off: aí o
    site sai sem CDN nem requisição externa nenhuma e abre sem internet.
    `style_block` é a personalidade do painel de Ajustes (nome, tom, tamanho).
    `fotos` são fotos reais do tema, para o site não usar imagem genérica.
    """
    if not memory_text:
        memory_text = _memory_block(message, use_memory)
    instruction = SYSTEM_PROMPT + FILE_INSTRUCTIONS
    if _looks_like_build(message):
        instruction += _design_rules(offline, fotos)
    return instruction + style_block + memory_text


def _project_for(conversation_id: int) -> str:
    """Pasta do projeto da conversa (cria se ainda não existir)."""
    conversation = db.get_conversation(conversation_id) or {}
    project = conversation.get("project")
    if not project:
        project = workspace.project_folder(
            conversation_id, conversation.get("title", "projeto")
        )
        db.set_project(conversation_id, project)
    return project


def _forget_conflicting(new_fact: str) -> None:
    """Apaga fatos antigos que o novo fato sobrescreve (mesmo tópico único).

    Só se aplica a informações de UM valor por vez: nome, idade, cidade,
    trabalho, estudo, relacionamento. Gostos e projetos são acumulativos e
    nunca entram aqui. Assim, "mudei pra SP" substitui "mora em RJ" em vez
    de deixar as duas respostas brigando na memória.
    """
    topic = _SINGLE_TOPIC(new_fact.lower())
    if not topic:
        return
    pattern = _SINGLE_TOPIC_PATTERNS[topic]
    for row in db.all_memories():
        old = row["content"]
        if pattern.search(old.lower()):
            db.delete_memory(row["id"])
            print(f"[memoria] atualizei (era '{old}')")


# Tópicos de "valor único" (um só por pessoa). Quando o fato novo casa com
# um desses, o antigo do mesmo tipo sai — sem isso a memória acumula
# respostas conflitantes ("se chama Edy" e "se chama Carlos" juntas).
_SINGLE_TOPIC_PATTERNS = {
    "nome": re.compile(
        r"\b(se chama|nome|chamad[oa]|se apelida|prefere ser chamad[oa])\b"
    ),
    "idade": re.compile(r"\b(idade|anos de idade|nasceu|aniversário|nascido)\b"),
    "cidade": re.compile(
        r"\b(mora|mudou-se|mudou|residente|vive|cidade|estado|país|bairro)\b"
    ),
    "trabalho": re.compile(
        r"\b(trabalha|trabalhou|emprego|profissão|cargo|função|empregad[oa]|"
        r"freelancer|empreend[eo]|dono de|atua como|se dedica a)\b"
    ),
    "estudo": re.compile(
        r"\b(estuda|estudou|cursa|faculdade|universidade|curso|formad[oa]|escola)\b"
    ),
    "relacionamento": re.compile(
        r"\b(casad[oa]|solteir[oa]|namorand[o]|divorciad[oa]|viúv[oa]|"
        r"companheir[oa]|esposa|marido|namorad[a])\b"
    ),
}


def _SINGLE_TOPIC(text: str) -> str | None:
    """Devolve o tópico único do fato, ou None se for acumulativo."""
    for topic, pattern in _SINGLE_TOPIC_PATTERNS.items():
        if pattern.search(text):
            return topic
    return None


def _learn(conversation_id: int, message: str, reply: str) -> None:
    """Guarda fatos novos sobre o usuário (roda fora do fluxo da resposta)."""
    if gemini is None:
        return

    clean_reply = workspace.strip_files(reply)
    try:
        facts = gemini.extract_memories(message, clean_reply)
    except Exception as exc:  # noqa: BLE001 - aprender é opcional
        print(f"[memoria] não deu para aprender agora: {str(exc)[:160]}")
        return

    for fact in facts:
        try:
            vector = gemini.embed(fact)
            if memory.is_duplicate(vector):
                continue
            # Fato de valor único ("mora em X", "se chama Y") SUBSTITUI o
            # antigo do mesmo tipo — senão a IA fica com respostas conflitantes
            # (dois nomes, duas cidades) na memória.
            _forget_conflicting(fact)
            memory.add(conversation_id, fact, vector)
            print(f"[memoria] lembrei: {fact}")
        except Exception as exc:  # noqa: BLE001
            print(f"[memoria] falha ao guardar: {str(exc)[:160]}")
            continue


def _learn_in_background(conversation_id: int, message: str, reply: str) -> None:
    threading.Thread(
        target=_learn,
        args=(conversation_id, message, reply),
        daemon=True,
    ).start()


def _needs_agent(message: str) -> bool:
    """True quando o pedido precisa de ferramentas (arquivos + terminal)."""
    if not AGENT_ENABLED or gemini is None:
        return False
    return bool(_AGENT_TRIGGER.search(message or ""))


def _collect_files(
    conversation_id: int, reply: str, agent_state: "agent.AgentState | None"
) -> tuple[str | None, list[dict]]:
    """Arquivos da resposta: do agente (já gravados) ou dos blocos ```file:```.

    O agente NÃO grava arquivo por ferramenta: ele devolve o código em blocos
    ```file:``` na resposta, igual à conversa comum. Então o caminho do agente
    só vale quando ele REALMENTE gravou algo; se gravou nada (só chamou
    `imagens`/`guia` e respondeu com o bloco), cai no mesmo extrator da resposta
    — senão o site era gerado no texto e nunca chegava ao disco.
    """
    if agent_state is not None and agent_state.files:
        return agent_state.project, agent_state.files
    return _save_generated_files(conversation_id, reply)


def _save_generated_files(
    conversation_id: int, reply: str
) -> tuple[str | None, list[dict]]:
    """Grava na pasta do projeto os arquivos que a IA escreveu na resposta.

    Devolve (nome_do_projeto, lista_de_arquivos).
    """
    files = workspace.extract_files(reply)
    if not files:
        return None, []

    project = _project_for(conversation_id)

    try:
        return project, workspace.write_files(project, files)
    except Exception as exc:  # noqa: BLE001 - não deixa a resposta falhar por isso
        print(f"[workspace] falha ao gravar arquivos: {exc}")
        return None, []


def _friendly_error(exc: Exception) -> tuple[str, str]:
    """Traduz os erros mais comuns da API para algo que o usuário entenda.

    Devolve (mensagem, tipo), onde tipo é "limit" (cota — algo que passa
    sozinho) ou "error" (falha de verdade). O front usa isso para escolher a
    cor do aviso e mostrar (ou não) o botão de tentar de novo.
    """
    text = str(exc)
    lowered = text.lower()
    flat = lowered.replace("_", "").replace(" ", "")

    # Mensagens próprias do cliente (todos os modelos de castigo).
    if "cota gratuita de hoje acabou" in lowered or "modelos estão ocupados" in lowered:
        return (text, "limit")

    if "resourceexhausted" in flat or "429" in text or "quota" in lowered:
        if "perday" in flat or "daily" in flat:
            return (
                "A cota gratuita de hoje acabou para todos os modelos. "
                "Amanhã ela volta sozinha — ou ative o faturamento no Google AI Studio para ficar sem limite.",
                "limit",
            )
        return (
            "O Google pediu para esperar alguns segundos (muitos pedidos juntos). "
            "Tente de novo em instantes.",
            "limit",
        )

    if "notfound" in flat or "no longer available" in lowered:
        return (
            "O modelo configurado não está disponível para esta conta. "
            "Confira o GEMINI_MODEL no backend/.env.",
            "error",
        )

    if "apikey" in flat or "api key" in lowered or "permission" in lowered:
        return (
            "A chave de API parece inválida ou sem permissão. "
            "Confira a GEMINI_API_KEY no backend/.env.",
            "error",
        )

    if "unauthenticated" in lowered:
        return (
            "A chave de API parece inválida ou sem permissão. "
            "Confira a GEMINI_API_KEY no backend/.env.",
            "error",
        )

    return (f"Não deu para falar com o Gemini agora: {text[:200]}", "error")


def _sse(payload: dict) -> str:
    """Formata um evento no padrão Server-Sent Events."""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _provider_options() -> list[dict]:
    """Opções do seletor de modelo no topo da tela."""
    return [
        {
            "id": "auto",
            "model": GEMINI_MODEL,
            "hint": "Responde pelo Gemini (Google).",
            "available": gemini is not None,
        }
    ]


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "model": GEMINI_MODEL,
        "models": GEMINI_MODELS,
        "memory_model": MEMORY_MODELS[0],
        "embedding_model": EMBEDDING_MODEL,
        "api_key_configured": gemini is not None,
        "provider_options": _provider_options(),
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request, cliente: "GeminiClient | None" = Depends(_cliente_da_requisicao)) -> ChatResponse:
    if cliente is None:
        raise HTTPException(status_code=401, detail="chave-api: Cole sua chave da API do Google Gemini (https://aistudio.google.com/apikey) para usar a Nébula.")
    _use = cliente
    _check_attachments(req.attachments)
    # Só exige texto numa mensagem nova; regenerar/editar reaproveitam a antiga.
    if not req.regenerate and req.edit_message_id is None:
        if not req.message.strip() and not req.attachments:
            raise HTTPException(status_code=422, detail="Mensagem vazia.")

    conversation_id, history, created, message, attachments, ja_salva = _resolve_turn(req)
    used_model: str | None = None

    def remember_model(name: str) -> None:
        nonlocal used_model
        used_model = name

    # Atalho para mensagens triviais: responde na hora, sem Gemini e sem
    # busca na memória (que custaria uma chamada de API à toa).
    trivial = _trivial_reply(message, attachments)
    if trivial is not None:
        if not ja_salva:
            db.add_message(conversation_id, "user", message, attachments or None)
        db.add_message(conversation_id, "model", trivial)
        return ChatResponse(conversation_id=conversation_id, reply=trivial)

    # Edição da última imagem ("mude a cor pra vermelho", "tire o fundo").
    # Mesmo caminho do /api/chat/stream — antes da geração, sem cair no modelo.
    if (
        not req.regenerate
        and req.edit_message_id is None
        and message.strip()
        and not _AGENT_TRIGGER.search(message)
        and _looks_like_image_edit(message)
    ):
        edited = _try_image_edit(conversation_id, message)
        if edited is None:
            target = _last_image_bytes(conversation_id)
            edit_reply = (
                _IMAGE_EDIT_FAIL_REPLY
                if target is not None
                else _IMAGE_NO_EDIT_TARGET_REPLY
            )
        else:
            edit_url = _edit_image_url(conversation_id, edited)
            edit_reply = (
                f"![imagem editada]({edit_url})"
                if edit_url
                else _IMAGE_EDIT_FAIL_REPLY
            )
        if not ja_salva:
            db.add_message(conversation_id, "user", message, attachments or None)
        db.add_message(conversation_id, "model", edit_reply)
        return ChatResponse(conversation_id=conversation_id, reply=edit_reply)

    # Mesmo caminho de imagem do /api/chat/stream (botão "+" → "Gerar imagem").
    if (
        not req.regenerate
        and req.edit_message_id is None
        and message.strip()
        and (req.image or _looks_like_image(message))
    ):
        image_url = _try_image(conversation_id, message)
        if not ja_salva:
            db.add_message(conversation_id, "user", message, attachments or None)
        if image_url is None:
            # Geradores no limite/fora do ar: responde a verdade em vez de
            # chamar o modelo, que inventava um link de imagem quebrado.
            db.add_message(conversation_id, "model", _IMAGE_FAIL_REPLY)
            return ChatResponse(
                conversation_id=conversation_id, reply=_IMAGE_FAIL_REPLY
            )
        image_reply = f"![imagem gerada]({image_url})"
        db.add_message(conversation_id, "model", image_reply)
        return ChatResponse(conversation_id=conversation_id, reply=image_reply)

    memory_text = _memory_block(message, req.use_memory)
    fotos = _fotos_do_pedido(message, req.offline, _contexto_do_pedido(history))
    instruction = _build_instruction(
        message, req.use_memory, memory_text, req.offline, _style_block(req), fotos
    )

    try:
        pieces = _reply_pieces(
            instruction,
            history,
            message,
            remember_model,
            attachments=_gemini_attachments(attachments),
            thinking_budget=_thinking_budget(message),
        )
        collected = [piece for piece in pieces if isinstance(piece, str)]
        reply = "".join(collected).strip()
        if not reply:
            raise RuntimeError("O modelo retornou uma resposta vazia.")
    except Exception as exc:  # noqa: BLE001 - repassa erro legível ao front
        if created:
            db.delete_conversation(conversation_id)
        raise HTTPException(status_code=502, detail=_friendly_error(exc)[0])

    if not ja_salva:
        db.add_message(conversation_id, "user", message, attachments or None)
    db.add_message(conversation_id, "model", reply)

    project, files = _save_generated_files(conversation_id, reply)
    _learn_in_background(conversation_id, message, reply)

    return ChatResponse(
        conversation_id=conversation_id,
        reply=reply,
        model=used_model,
        project=project,
        files=files,
    )


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest, request: Request, cliente: "GeminiClient | None" = Depends(_cliente_da_requisicao)) -> StreamingResponse:
    """Igual ao /api/chat, mas envia a resposta em pedaços (streaming).

    Eventos enviados:
      {"type": "meta",   "conversation_id": 1}
      {"type": "status", "stage": "thinking"|"tool"}
      {"type": "delta",  "text": "..."}
      {"type": "sources", "sources": [{"title": "...", "url": "..."}]}
      {"type": "files",  "files": [{"name": "index.html", "url": "...", "lines": 30}]}
      {"type": "error",  "message": "..."}
      {"type": "done"}
    """
    if cliente is None:
        raise HTTPException(status_code=401, detail="chave-api: Cole sua chave da API do Google Gemini (https://aistudio.google.com/apikey) para usar a Nébula.")
    _use = cliente
    _check_attachments(req.attachments)
    if not req.regenerate and req.edit_message_id is None:
        if not req.message.strip() and not req.attachments:
            raise HTTPException(status_code=422, detail="Mensagem vazia.")

    conversation_id, history, created, message, attachments, ja_salva = _resolve_turn(req)

    # Atalho para mensagens triviais: responde na hora, sem Gemini e sem
    # busca na memória. A gravação no banco acontece ANTES do stream, para
    # não perder a mensagem se o cliente desconectar no meio.
    trivial = _trivial_reply(message, attachments)
    if trivial is not None:
        if not ja_salva:
            db.add_message(conversation_id, "user", message, attachments or None)
        db.add_message(conversation_id, "model", trivial)

        def _fast_stream() -> Iterator[str]:
            yield _sse({"type": "meta", "conversation_id": conversation_id})
            yield _sse({"type": "delta", "text": trivial})
            yield _sse({"type": "done", "model": None})

        return StreamingResponse(
            _fast_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Edição da última imagem ("mude a cor pra vermelho", "tire o fundo").
    # Vem antes da geração: se o pedido for de edição, NUNCA cai no modelo —
    # ele re-imitaria o formato do link e inventaria um arquivo quebrado.
    # Responde com a foto editada ou com a verdade, e sai daqui.
    if (
        not req.regenerate
        and req.edit_message_id is None
        and message.strip()
        and not _AGENT_TRIGGER.search(message)
        and _looks_like_image_edit(message)
    ):
        edited = _try_image_edit(conversation_id, message)
        if edited is None:
            target = _last_image_bytes(conversation_id)
            edit_reply = (
                _IMAGE_EDIT_FAIL_REPLY
                if target is not None
                else _IMAGE_NO_EDIT_TARGET_REPLY
            )
            edit_url = None
        else:
            edit_url = _edit_image_url(conversation_id, edited)
            edit_reply = (
                f"![imagem editada]({edit_url})" if edit_url else _IMAGE_EDIT_FAIL_REPLY
            )

        if not ja_salva:
            db.add_message(conversation_id, "user", message, attachments or None)
        db.add_message(conversation_id, "model", edit_reply)

        def _edit_stream() -> Iterator[str]:
            yield _sse({"type": "meta", "conversation_id": conversation_id})
            yield _sse({"type": "delta", "text": edit_reply})
            yield _sse({"type": "done", "model": None})

        return StreamingResponse(
            _edit_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Pedido curto de imagem ("desenhe um gato", "gere uma foto de praia"):
    # gera com o modelo de imagem e responde com a foto em markdown. Se a
    # cota de imagem estiver no fim, segue o caminho normal e o modelo
    # responde em texto — nunca trava o usuário por causa de imagem.
    if (
        not req.regenerate
        and req.edit_message_id is None
        and message.strip()
        and (req.image or _looks_like_image(message))
    ):
        image_url = _try_image(conversation_id, message)
        if not ja_salva:
            db.add_message(conversation_id, "user", message, attachments or None)

        # Certo ou errado, a resposta sai pronta daqui: falhou, a Nébula conta
        # na hora (o modelo não chega a inventar um link de imagem quebrado).
        image_reply = (
            f"![imagem gerada]({image_url})" if image_url else _IMAGE_FAIL_REPLY
        )
        db.add_message(conversation_id, "model", image_reply)

        def _image_stream() -> Iterator[str]:
            yield _sse({"type": "meta", "conversation_id": conversation_id})
            yield _sse({"type": "delta", "text": image_reply})
            yield _sse({"type": "done", "model": None})

        return StreamingResponse(
            _image_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    memory_text = _memory_block(message, req.use_memory)
    fotos = _fotos_do_pedido(message, req.offline, _contexto_do_pedido(history))
    instruction = _build_instruction(
        message, req.use_memory, memory_text, req.offline, _style_block(req), fotos
    )

    # Modo agente: o pedido envolve compilar/executar/instalar — aí a IA usa
    # ferramentas de arquivo e terminal até a tarefa ficar pronta.
    use_agent = _needs_agent(message)
    agent_state: agent.AgentState | None = None
    agent_project: str | None = None
    if use_agent:
        instruction += AGENT_INSTRUCTIONS
        agent_project = _project_for(conversation_id)
        agent_state = agent.AgentState(agent_project)

    def event_stream() -> Iterator[str]:
        collected: list[str] = []
        error: str | None = None
        error_kind = "error"
        saved_files: list[dict] = []
        saved_project: str | None = None
        used_model: str | None = None

        def remember_model(name: str) -> None:
            nonlocal used_model
            used_model = name

        # Fontes da busca na web (chegam antes do "done").
        sources: list[dict] = []

        def remember_sources(items: list[dict]) -> None:
            nonlocal sources
            sources = items

        yield _sse({"type": "meta", "conversation_id": conversation_id})

        try:
            if use_agent and agent_state is not None:
                # Laço do agente: pensa -> chama ferramenta -> repete. Cada
                # evento (status, tool, approval, delta) vira um SSE na hora.
                for event in agent.run(
                    _use,
                    instruction,
                    history,
                    message,
                    _gemini_attachments(attachments),
                    agent_project or "",
                    agent_state,
                    thinking_budget=_thinking_budget(message),
                ):
                    kind = event.get("type")
                    if kind == "error":
                        error = str(event.get("message") or "Erro no agente.")
                        error_kind = str(event.get("kind") or "error")
                        break
                    if kind == "model":
                        remember_model(event.get("model"))
                        continue
                    if kind == "delta":
                        collected.append(str(event.get("text") or ""))
                    yield _sse(event)
            else:
                for piece in _reply_pieces(
                    instruction,
                    history,
                    message,
                    on_model=remember_model,
                    attachments=_gemini_attachments(attachments),
                    thinking_budget=_thinking_budget(message),
                    # Busca só quando não é pedido de site/código (aí o thinking
                    # entra, e o combinado é usar um ou outro).
                    search=_thinking_budget(message) == 0,
                    on_sources=remember_sources,
                    cliente=_use,
                ):
                    collected.append(piece)
                    yield _sse({"type": "delta", "text": piece})
        except Exception as exc:  # noqa: BLE001 - repassa erro legível ao front
            error, error_kind = _friendly_error(exc)
        finally:
            # Salva o que foi gerado mesmo se o usuário fechar a aba no meio.
            # (o finally roda também quando o cliente desconecta)
            reply = "".join(collected)
            reply_clean = reply.strip()
            try:
                if db.conversation_exists(conversation_id):
                    if not ja_salva and (reply_clean or reply):
                        db.add_message(
                            conversation_id, "user", message, attachments or None
                        )
                    if reply_clean or reply:
                        db.add_message(conversation_id, "model", reply_clean or reply)
                    saved_project, saved_files = _collect_files(
                        conversation_id, reply_clean or reply, agent_state
                    )
                    _learn_in_background(conversation_id, message, reply_clean or reply)
                elif created and (reply_clean or reply):
                    if not ja_salva:
                        db.add_message(
                            conversation_id, "user", message, attachments or None
                        )
                    db.add_message(conversation_id, "model", reply_clean or reply)
                    saved_project, saved_files = _collect_files(
                        conversation_id, reply_clean or reply, agent_state
                    )
                    _learn_in_background(conversation_id, message, reply_clean or reply)
                elif created:
                    db.delete_conversation(conversation_id)
            except Exception as exc:  # noqa: BLE001 - nunca derruba o stream
                print(f"[stream] falha ao salvar a resposta: {exc}")

        if use_agent and agent_state is not None and not used_model:
            used_model = agent_state.model

        if error:
            yield _sse({"type": "error", "message": error, "kind": error_kind})
            return

        if not collected:
            yield _sse(
                {
                    "type": "error",
                    "message": "A Nébula não retornou texto. Tente enviar de novo.",
                    "kind": "error",
                }
            )
            return

        if sources:
            yield _sse({"type": "sources", "sources": sources})

        if saved_files:
            yield _sse(
                {
                    "type": "files",
                    "project": saved_project,
                    "files": saved_files,
                }
            )

        yield _sse({"type": "done", "model": used_model})

        # Vai junto com o fim da resposta: a cópia COMPLETA do banco agora.
        # O site guarda no aparelho imediatamente — sem depender de outra
        # requisição. É o que protege as conversas do reinício do servidor.
        try:
            yield _sse(
                {
                    "type": "cofre",
                    "dados": base64.b64encode(backup.exportar()).decode("ascii"),
                }
            )
        except Exception as exc:  # noqa: BLE001 - nunca derruba o stream
            print(f"[stream] falha ao montar o cofre: {exc}")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # evita buffer em proxies
        },
    )


@app.get("/api/conversations")
def list_conversations() -> list[dict]:
    return db.list_conversations()


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: int) -> dict:
    conversation = db.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    return {
        "project": conversation.get("project"),
        "messages": _clean_history(db.get_messages(conversation_id)),
    }


@app.delete("/api/conversations/{conversation_id}")
def remove_conversation(conversation_id: int) -> dict:
    if not db.delete_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    return {"deleted": conversation_id}


@app.patch("/api/conversations/{conversation_id}")
def rename_conversation(conversation_id: int, req: RenameRequest) -> dict:
    """Renomeia a conversa (menu de contexto, como no app do Gemini)."""
    title = req.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Título vazio.")
    if not db.rename_conversation(conversation_id, title):
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    return {"id": conversation_id, "title": title}


@app.get("/api/files")
def list_files() -> list[dict]:
    """Projetos gerados com título e conversa de origem (biblioteca)."""
    titles = {item["id"]: item["title"] for item in db.list_conversations()}
    projects: list[dict] = []
    for item in workspace.list_projects():
        # Pasta slug-{id da conversa} (ver workspace.project_folder).
        match = re.search(r"-(\d+)$", item["project"])
        conversation_id = int(match.group(1)) if match else None
        title = titles.get(conversation_id)
        if not title:
            title = item["project"].rsplit("-", 1)[0].replace("-", " ")
        projects.append(
            {**item, "conversation_id": conversation_id, "title": title}
        )
    return projects


@app.get("/api/files/{project}/zip")
def download_project_zip(project: str) -> StreamingResponse:
    """Baixa o projeto inteiro (HTML/CSS/JS) em um .zip só."""
    base = workspace.workspace_dir().resolve()
    folder = (base / project).resolve()
    # Sem travessia de diretório: só pastas diretas dentro do workspace.
    if folder.parent != base or not folder.is_dir():
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(folder).as_posix())
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{folder.name}.zip"'
        },
    )


@app.post("/api/approvals")
def approve_command(decision: ApprovalDecision) -> dict:
    """Usuário aprovou/negou um comando que estava esperando no chat."""
    if not agent.resolve_approval(decision.id, decision.approved):
        raise HTTPException(
            status_code=404,
            detail="Este pedido expirou ou já foi respondido.",
        )
    return {"ok": True, "approved": decision.approved}


@app.get("/api/memories")
def list_memories() -> list[dict]:
    return db.list_memories()


@app.delete("/api/memories/{memory_id}")
def remove_memory(memory_id: int) -> dict:
    if not db.delete_memory(memory_id):
        raise HTTPException(status_code=404, detail="Memória não encontrada.")
    return {"deleted": memory_id}


# ------------------------------------------------- cópia de segurança (cofre)
# O plano grátis do Render apaga o disco a cada reinício. Estas rotas deixam
# o site guardar/restaurar o histórico numa cópia que fica FORA do servidor.


class CofreRecebido(BaseModel):
    dados: str = Field(..., description="Banco em base64, vindo do cofre.")


@app.get("/api/backup/export")
def backup_export() -> dict:
    """Devolve o banco inteiro (base64) para o site guardar no cofre."""
    return {
        "dados": base64.b64encode(backup.exportar()).decode("ascii"),
        "estatisticas": backup.estatisticas(),
    }


@app.post("/api/backup/import")
def backup_import(payload: CofreRecebido) -> dict:
    """Restaura o banco a partir de uma cópia guardada no cofre."""
    try:
        dados = base64.b64decode(payload.dados, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Cópia inválida (base64).")
    try:
        backup.importar(dados)
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro))
    return {"ok": True, "restaurado": backup.estatisticas()}


@app.get("/api/backup/status")
def backup_status() -> dict:
    """Diz se o banco está vazio (sinal de que houve reinício)."""
    return {"vazio": backup.banco_vazio(), "estatisticas": backup.estatisticas()}


# ------------------------------------------------ servir o site (deploy)
# No deploy (Render/Fly) o backend também entrega o frontend compilado, para
# tudo ficar numa URL só ("entra e usa"), sem CORS e sem dois endereços.
# Localmente nada muda: o Vite continua servindo a interface em :5173.
# Ativa só se a pasta do site existir (FRONTEND_DIST ou ./static).
_DIST = Path(os.getenv("FRONTEND_DIST", str(Path(__file__).parent / "static")))
if _DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_DIST / "assets")), name="assets")

    @app.get("/{caminho:path}")
    def _site(caminho: str):
        """Entrega o site; rotas do app voltam pro index.html (SPA)."""
        if caminho.startswith("api/") or caminho.startswith("files/"):
            raise HTTPException(status_code=404, detail="Não encontrado.")
        alvo = (_DIST / caminho).resolve()
        if _DIST.resolve() in alvo.parents and alvo.is_file():
            return FileResponse(alvo)
        return FileResponse(_DIST / "index.html")
