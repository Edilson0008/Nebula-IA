"""Ferramentas de tempo real: clima, hora, notícias e busca na web.

Tudo gratuito e SEM chave de API (nada de cadastro, nada de .env novo):
- clima    -> Open-Meteo (geocoding + previsão)
- noticias -> RSS do Google Notícias (pt-BR, do dia ou por assunto)
- buscar   -> resposta instantânea do DuckDuckGo + resultados do Bing (RSS)
- hora     -> relógio do sistema + fusos (zoneinfo), sem rede nenhuma

Cada função devolve texto pronto em português (o agente repassa direto pro
modelo). Falha de rede vira exceção com mensagem amigável — quem chama
(trata) converte em resposta honesta: "sem internet agora".
"""

import html as html_lib
import os
import re
import unicodedata
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

import httpx

# Unsplash (opcional) — melhor para foto por item exato
# Crie uma app em https://unsplash.com/developers e coloque UNSPLASH_ACCESS_KEY no .env
_UNSPLASH_URL = "https://api.unsplash.com/search/photos"

# Parece navegador de verdade: alguns CDNs recusam clientes "pelados".
_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}
_TIMEOUT = 15.0
_MAX_CHARS = 2400  # resposta curta: entra no contexto do modelo sem pesar


def _get(url: str, params: dict | None = None) -> httpx.Response:
    """GET com navegação, timeout e erro claro quando a rede falha."""
    try:
        response = httpx.get(
            url, params=params, headers=_UA, timeout=_TIMEOUT, follow_redirects=True
        )
        response.raise_for_status()
        return response
    except httpx.HTTPError as exc:
        raise RuntimeError(f"sem resposta da internet ({exc.__class__.__name__})") from exc


def _clip(text: str, limit: int = _MAX_CHARS) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _sem_acento(texto: str) -> str:
    """'São Paulo' -> 'sao paulo' (pra achar fuso sem depender de acento)."""
    bruto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in bruto if unicodedata.category(c) != "Mn").lower()


def _sem_html(texto: str) -> str:
    return html_lib.unescape(re.sub(r"<[^>]+>", "", texto or "")).strip()


# --------------------------------------------------------------------- clima

# Códigos WMO (Open-Meteo) em português.
_WMO = {
    0: "céu limpo",
    1: "predominantemente limpo",
    2: "parcialmente nublado",
    3: "encoberto",
    45: "nevoeiro",
    48: "nevoeiro com geada",
    51: "garoa fraca",
    53: "garoa",
    55: "garoa forte",
    56: "garoa congelante",
    57: "garoa congelante forte",
    61: "chuva fraca",
    63: "chuva",
    65: "chuva forte",
    66: "chuva congelante",
    67: "chuva congelante forte",
    71: "neve fraca",
    73: "neve",
    75: "neve forte",
    77: "grãos de neve",
    80: "pancadas de chuva",
    81: "pancadas de chuva",
    82: "pancadas de chuva fortes",
    85: "pancadas de neve",
    86: "pancadas de neve fortes",
    95: "tempestade",
    96: "tempestade com granizo",
    99: "tempestade forte com granizo",
}


def clima(local: str, unidade: str = "c") -> str:
    """Tempo agora + hoje/amanhã de uma cidade, em português."""
    local = (local or "").strip()
    if not local:
        return "me diga a cidade, tipo `clima: São Paulo`."

    geo = _get(
        "https://geocoding-api.open-meteo.com/v1/search",
        {"name": local, "count": 1, "language": "pt", "format": "json"},
    ).json()
    results = geo.get("results") or []
    if not results:
        return f"não achei nenhum lugar chamado «{local}» — tente outro nome ou país."

    lugar = results[0]
    nome = lugar.get("name") or local
    regiao = lugar.get("admin1") or lugar.get("country") or ""
    onde = f"{nome}" + (f" — {regiao}" if regiao and regiao != nome else "")

    fahrenheit = str(unidade).lower().startswith("f")
    atual = (
        "temperature_2m,apparent_temperature,relative_humidity_2m,"
        "weather_code,wind_speed_10m"
    )
    diario = "temperature_2m_max,temperature_2m_min,precipitation_probability_max"
    dados = _get(
        "https://api.open-meteo.com/v1/forecast",
        {
            "latitude": lugar["latitude"],
            "longitude": lugar["longitude"],
            "current": atual,
            "daily": diario,
            "timezone": "auto",
            "forecast_days": 2,
            "temperature_unit": "fahrenheit" if fahrenheit else "celsius",
            "wind_speed_unit": "mph" if fahrenheit else "kmh",
        },
    ).json()

    agora = dados.get("current") or {}
    dias = dados.get("daily") or {}
    grau = "°F" if fahrenheit else "°C"
    vento = "mph" if fahrenheit else "km/h"
    condicao = _WMO.get(agora.get("weather_code"), "condição não catalogada")

    linhas = [f"Clima em {onde}:"]
    linhas.append(
        f"Agora: {agora.get('temperature_2m')}{grau} "
        f"(sensação {agora.get('apparent_temperature')}{grau}), {condicao}, "
        f"umidade {agora.get('relative_humidity_2m')}%, "
        f"vento {agora.get('wind_speed_10m')} {vento}."
    )
    nomes_dias = ("Hoje", "Amanhã")
    for i, dia_nome in enumerate(nomes_dias):
        if i >= len(dias.get("time") or []):
            break
        linhas.append(
            f"{dia_nome} ({dias['time'][i]}): mín {dias['temperature_2m_min'][i]}"
            f"{grau} / máx {dias['temperature_2m_max'][i]}{grau}, chuva "
            f"{(dias.get('precipitation_probability_max') or ['-']*2)[i]}%."
        )
    return _clip("\n".join(linhas))


# ---------------------------------------------------------------------- hora

_DIAS_SEMANA = (
    "segunda-feira", "terça-feira", "quarta-feira",
    "quinta-feira", "sexta-feira", "sábado", "domingo",
)
_MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)

# Apelidos comuns -> IANA. O apelido é comparado SEM acento.
_FUSOS = {
    "brasil": "America/Sao_Paulo", "brasilia": "America/Sao_Paulo",
    "sao paulo": "America/Sao_Paulo", "rio de janeiro": "America/Sao_Paulo",
    "rio": "America/Sao_Paulo", "salvador": "America/Bahia",
    "fortaleza": "America/Fortaleza", "recife": "America/Recife",
    "manaus": "America/Manaus", "belem": "America/Belem",
    "porto alegre": "America/Sao_Paulo", "curitiba": "America/Sao_Paulo",
    "brasilia df": "America/Sao_Paulo", "noronha": "America/Noronha",
    "nova york": "America/New_York", "eua": "America/New_York",
    "estados unidos": "America/New_York", "los angeles": "America/Los_Angeles",
    "california": "America/Los_Angeles", "chicago": "America/Chicago",
    "miami": "America/New_York", "toronto": "America/Toronto",
    "mexico": "America/Mexico_City", "argentina": "America/Argentina/Buenos_Aires",
    "buenos aires": "America/Argentina/Buenos_Aires", "chile": "America/Santiago",
    "santiago": "America/Santiago", "colombia": "America/Bogota",
    "bogota": "America/Bogota", "peru": "America/Lima", "lima": "America/Lima",
    "venezuela": "America/Caracas", "equador": "America/Guayaquil",
    "londres": "Europe/London", "inglaterra": "Europe/London",
    "reino unido": "Europe/London", "lisboa": "Europe/Lisbon",
    "portugal": "Europe/Lisbon", "paris": "Europe/Paris",
    "franca": "Europe/Paris", "madri": "Europe/Madrid",
    "espanha": "Europe/Madrid", "roma": "Europe/Rome", "italia": "Europe/Rome",
    "berlim": "Europe/Berlin", "alemanha": "Europe/Berlin",
    "amsterdam": "Europe/Amsterdam", "moscou": "Europe/Moscow",
    "russia": "Europe/Moscow", "utc": "UTC", "gmt": "UTC",
    "tokio": "Asia/Tokyo", "japao": "Asia/Tokyo", "pequim": "Asia/Shanghai",
    "china": "Asia/Shanghai", "hong kong": "Asia/Hong_Kong",
    "seul": "Asia/Seul", "coreia": "Asia/Seul", "india": "Asia/Kolkata",
    "dubai": "Asia/Dubai", "emirados": "Asia/Dubai",
    "australia": "Australia/Sydney", "sydney": "Australia/Sydney",
    "nova zelandia": "Pacific/Auckland",
    "toquio": "Asia/Tokyo", "tokio": "Asia/Tokyo",
}


def _resolver_fuso(pedido: str) -> tuple[ZoneInfo, str]:
    """Acha o fuso: apelido em português, nome IANA, ou erro explicando."""
    limpo = _sem_acento((pedido or "").strip())
    if not limpo:
        return ZoneInfo("America/Sao_Paulo"), "Brasília (horário do Brasil)"

    if limpo in _FUSOS:
        nome_iana = _FUSOS[limpo]
        return ZoneInfo(nome_iana), pedido.strip()

    # Caminho IANA direto ("America/New_York", "Europe/Lisbon"...).
    for candidato in (pedido.strip(), pedido.strip().replace(" ", "_")):
        try:
            return ZoneInfo(candidato), candidato
        except Exception:  # noqa: BLE001 - não é IANA, tenta o próximo
            continue
    raise ValueError(
        f"não conheço o fuso «{pedido}» — tente um apelido (Tóquio, Lisboa, "
        "Nova York) ou o nome técnico (America/New_York)."
    )


def hora(fuso: str = "") -> str:
    """Data e hora atuais em qualquer fuso (padrão: Brasília)."""
    try:
        zone, rotulo = _resolver_fuso(fuso)
    except ValueError as exc:
        return str(exc)
    agora = datetime.now(zone)
    return (
        f"Agora em {rotulo}: {agora:%H:%M} de {_DIAS_SEMANA[agora.weekday()]}, "
        f"{agora.day} de {_MESES[agora.month - 1]} de {agora.year} "
        f"(fuso {zone.key})."
    )


# ------------------------------------------------------------------ noticias


def _itens_rss(url: str, params: dict, quantidade: int) -> list[tuple[str, str, str]]:
    """Baixa um RSS e devolve (título, detalhe, link) de cada item, já limpos."""
    xml = _get(url, params).text
    import xml.etree.ElementTree as ET

    try:
        raiz = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise RuntimeError(f"o RSS veio ilegível ({exc})") from exc

    itens: list[tuple[str, str, str]] = []
    for item in raiz.iter("item"):
        if len(itens) >= quantidade:
            break
        titulo = _sem_html(item.findtext("title") or "")
        if not titulo:
            continue
        fonte = _sem_html(item.findtext("source") or "")
        quando = ""
        data = item.findtext("pubDate") or ""
        if data:
            try:
                instante = parsedate_to_datetime(data)
                quando = f"{instante.day}/{instante.month:02d} {instante:%H:%M}"
            except (TypeError, ValueError):
                quando = ""
        detalhe = " \u2014 ".join(x for x in (fonte, quando) if x)
        itens.append((titulo, detalhe, (item.findtext("link") or "").strip()))
    return itens


def _montar_itens(itens: list[tuple[str, str, str]]) -> list[str]:
    linhas: list[str] = []
    for i, (titulo, detalhe, link) in enumerate(itens):
        linhas.append(f"{i + 1}. {titulo}" + (f" ({detalhe})" if detalhe else ""))
        if link:
            linhas.append(f"   {link}")
    return linhas


def noticias(tema: str = "", quantidade: int = 5) -> str:
    """Manchetes atuais (Google Notícias pt-BR), do dia ou de um assunto."""
    tema = (tema or "").strip()
    quantidade = max(3, min(10, int(quantidade or 5)))
    if tema:
        url = "https://news.google.com/rss/search"
        params = {"q": tema, "hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"}
        cabeca = f"Notícias sobre «{tema}»:"
    else:
        url = "https://news.google.com/rss"
        params = {"hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"}
        cabeca = "Principais notícias de agora:"

    linhas = [cabeca] + _montar_itens(_itens_rss(url, params, quantidade))
    if len(linhas) == 1:
        linhas.append("não achei notícias para esse assunto agora.")
    return _clip("\n".join(linhas))


# -------------------------------------------------------------------- busca


def buscar(consulta: str, quantidade: int = 5) -> str:
    """Busca na web em tempo real.

    Cadeia: resumo do DuckDuckGo -> resultados do Bing (RSS) -> e, se o Bing
    vier vazio (consultas conversacionais), manchetes do Google Notícias com
    a mesma pergunta (costuma achar a resposta do dia).
    """
    consulta = (consulta or "").strip()
    if not consulta:
        return "me diga o que procurar."
    quantidade = max(3, min(8, int(quantidade or 5)))

    resumo = ""
    try:
        resposta = _get(
            "https://api.duckduckgo.com/",
            {"q": consulta, "format": "json", "no_html": 1},
        ).json()
        resumo = _sem_html(
            resposta.get("AbstractText")
            or resposta.get("Answer")
            or resposta.get("Definition")
        )
    except (RuntimeError, ValueError):
        pass  # resumo é um extra; a busca em si continua

    itens: list[tuple[str, str, str]] = []
    tentativa = "os buscadores"
    try:
        itens = _itens_rss(
            "https://www.bing.com/search",
            {"q": consulta, "format": "rss", "setlang": "pt"},
            quantidade,
        )
        tentativa = "o Bing"
    except RuntimeError as exc:
        ultimo_erro = exc
    else:
        ultimo_erro = None

    if not itens:
        try:
            itens = _itens_rss(
                "https://news.google.com/rss/search",
                {"q": consulta, "hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"},
                quantidade,
            )
            tentativa = "o Google Notícias"
        except RuntimeError as exc:
            ultimo_erro = exc

    if not itens and not resumo:
        raise RuntimeError(f"{tentativa} não responderam ({ultimo_erro})")

    linhas = [f"Resultados para «{consulta}»:"]
    if resumo:
        linhas.append(f"Resumo: {resumo}")
    if itens:
        linhas.append("Na web:")
        linhas.extend(_montar_itens(itens))
    return _clip("\n".join(linhas))


# -------------------------------------------------------------------- fotos

# Fotos REAIS (licença livre) para os sites criados pela IA.
#
# Fonte PRINCIPAL: Openverse (api.openverse.org) — o buscador oficial de mídia
# Creative Commons. Ele busca por CONTEÚDO (Unsplash, Flickr CC, Wikimedia,
# NASA…), então "lua" acha fotos da Lua e "leão" acha o animal, sem depender do
# nome do arquivo. Fonte de RESERVA: Wikimedia Commons (filetype:bitmap), que
# é estável e não tem chave nenhuma.
_WIKI_UA = {
    "User-Agent": "NebulaApp/1.0 (app pessoal; contato: nebula@example.org)",
    "Accept": "application/json",
}
_OPENVERSE_URL = "https://api.openverse.org/v1/images/"
_FOTOS_CACHE: dict[str, list[dict]] = {}
_MAX_CACHE = 40

# Títulos que não podem entrar num site (busca livre não tem filtro etário).
_FOTO_BLOQUEIO = re.compile(
    r"(?i)\b(nud\w*|naked|topless|erotic|porn\w*|xxx|sex\w*|adult\w*)\b"
)

# Títulos que não são FOTO do tema: logotipo, capa de disco, série de TV,
# documento digitalizado, mapa antigo, brasão. São o lixo típico que o Commons
# devolve quando a busca não acha o assunto — e viravam "foto do site".
# (Nada de excluir por extensão ou data: foto de prédio antigo é foto boa.)
_FOTO_LIXO = re.compile(
    r"(?i)("
    r"\blogo\b|\blogotype\b|\bcoat of arms\b|\bbras[ãa]o\b|"
    r"\b(carta|mapa|manuscrito|gravura|litografia)\b|"
    r"\bTV series\b|\bs[ée]rie\b|\b(temporada|season)\b|"
    r"\bposter\b|\bcover art\b|"
    # Exposição/feira/museu: quando a busca é uma CATEGORIA ("animais raros"),
    # o acervo devolve estande de exposição, placa de museu, vitrine — nada a
    # ver com o bicho. Foto do tema é o bicho, não o evento.
    r"\b(exposi[çc][ãa]o|exposi[çc][õo]es|feira|feiras|mostra|mostras|"
    r"estande|pavilh[ãa]o|museu|acervo|vitrine|painel|banner)\b|"
    # Produto/hobby com o mesmo nome do tema: "galáxia" acha esmalte de unha
    # ("Unha 19 - Galáxias"), "leão" acha camisa de time. Foto do tema é o
    # assunto, não a mercadoria.
    r"\b(unha|unhas|manicure|esmalte|colorama|wallpaper|papel de parede|"
    r"adesivo|azulejo|estampa|molde|camisa|blusa|camiseta|caneca|"
    r"capa de celular|renda|bordado|vitral|pintura|quadro|gravur\w*)\b|"
    # Marca/produto com nome de coisa: "Ford Galáxia" (carro), "Pão de Açúcar"
    # (rede de mercado), "Star Wars" (filme). O assunto do bloco é a coisa,
    # não a marca que pegou o nome dela.
    r"\b(ford|chevrolet|volkswagen|fiat|toyota|honda|renault|peugeot|"
    r"star wars|star trek|p[ãa]o de a[çc][úu]car|kit carros)\b"
    r")"
)

# Palavras que NÃO ajudam a buscar foto: adjetivo de categoria ("animais
# raros", "flores bonitas", "produtos incríveis"). Buscar só o adjetivo traz
# exposição/museu; o que acha o bicho/produto é o substantivo concreto.
_TEMA_ADJETIVO = re.compile(
    r"(?i)\b(raros?|raras?|ex[óo]tic[oa]s?|bonit[oa]s?|incr[íi]ve(?:l|is)|"
    r"famos[oa]s?|amaz[ôo]nic[oa]s?|selvagens?|diferentes?|variados?|"
    r"diversos?|especiais?|interessantes?|curiosos?)\b"
)

# Palavra de marketing/qualidade: "bem profissional", "didático", "moderno",
# "premium". Não é coisa nenhuma — não existe foto de "moderno". Quando o
# agente pede foto com um tema assim, a busca devolve propaganda, quadro de
# museu ou paisagem aleatória: melhor não trazer foto.
_TEMA_MARKETING = {
    "bem", "profissional", "profissionais", "didatico", "didatica", "moderno",
    "moderna", "premium", "elegante", "sofisticado", "sofisticada", "criativo",
    "criativa", "atrativo", "atrativa", "impactante", "responsivo", "responsiva",
    "completo", "completa", "limpo", "limpa", "minimalista", "futurista",
    "inovador", "inovadora", "qualidade", "alto", "padrao", "conteudo",
    "informacao", "informacoes", "descricao", "texto", "detalhe", "detalhes",
    "atual", "novo", "nova", "top", "melhor", "otimo", "otima", "excelente",
    "incrivel", "incriveis", "raro", "raros", "rara", "raras", "bonito",
    "bonita", "especial", "especiais", "interessante", "curioso", "incriv",
}

# Categoria vazia: não é um bicho/produto, é um conjunto ("animais", "bichos",
# "coisas"). O acervo não tem "animal" genérico — tem o bicho. Se o termo
# sobrar só com isso, é melhor devolver nada (o site usa SVG ou a IA busca
# espécie por espécie) do que encher a página de foto aleatória (fresco de
# igreja, estande de museu, anúncio de 1931).
_TEMA_CATEGORIA = {
    "animais", "animal", "bichos", "bicho", "coisas", "coisa",
    "objetos", "objeto", "itens", "item", "pessoas", "pessoa",
}

# Palavras cujo sentido no Commons é OUTRO: "academia" acha academia de
# letras e My Hero Academia, "receita" acha Receita Federal, "pet" acha
# Pet Shop Boys. Aqui a EXPANSÃO é obrigatória — o título precisa trazer a
# palavra de contexto ("musculação", "comida", "cachorro") para valer.
_DESAMBIGUA = {
    "receita": "comida",
    "programacao": "computador",
    "musica": "show",
    "tecnologia": "computador",
    "academia": "musculação",
    "casamento": "noivos",
    # Numa pizzaria o site mostra o PRATO, não a fachada: "pizzaria" acha a
    # loja, "pizza" acha a comida. Idem para lanchonete/doceria/cafeteria.
    "pizzaria": "pizza",
    "lanchonete": "sanduíche",
    "doceria": "doces",
    "gelateria": "gelato",
    "sorveteria": "sorvete",
}

# Palavras que funcionam sozinhas, mas às vezes rendem mais com um sinônimo:
# aqui o termo PEDIDO vem primeiro e a expansão só completa o que faltar.
# ("floricultura" acha a floricultura de verdade, enquanto "flores" acha
# sobrenome de gente.)
_SINONIMOS = {
    "odonto": "dentista",
    "dentista": "dentista",
    "confeitaria": "doces",
    "cafeteria": "café",
    "padaria": "pão",
    "salao": "cabelo",
    "beleza": "cabelo",
    "barbearia": "barbearia",
    "advocacia": "escritório",
    "advogado": "escritório",
    "clinica": "médica",
    "moda": "roupas",
    "roupas": "roupas",
    "imobiliaria": "imóvel",
    "viagem": "turismo",
    "viagens": "turismo",
    "floricultura": "flores",
    "restaurante": "comida",
    "pet": "cachorro",
}

# Palavras cujo termo em PORTUGUÊS é homônimo de outra coisa no acervo. A
# busca em inglês acha o sentido que o site quer: "leão" acha "Carneiro Leão"
# (sobrenome de gente) e "Fábrica Leão" (empresa), mas "lion" acha o animal.
# "manga" acha roupa, "mango" acha a fruta; "banco" acha banco de praça e
# instituição financeira, "bench"/"bank" separa os dois.
# O valor pode ter mais de uma palavra ("leão" -> "lion animal").
# A chave é comparada sem acento e por prefixo de palavra.
_EM_INGLES = {
    "leao": "lion",
    "leoa": "lioness",
    "manga": "mango",
    "banco": "bench",
    "copo": "glass",
    "prato": "plate",
    "mesa": "table",
    "sapato": "shoe",
    "bolsa": "handbag",
    "coroa": "crown",
    "vestido": "dress",
    "anel": "ring",
    "cesta": "basket",
    "chave": "key",
    "rosa": "rose flower",
    "cravo": "carnation flower",
    "tigre": "tiger",
    "urso": "bear",
    "lobo": "wolf",
    "aguia": "eagle",
    "tartaruga": "turtle",
    "golfinho": "bottlenose dolphin",
    "tubarao": "shark",
    "abelha": "bee",
    "formiga": "ant",
    "borboleta": "butterfly",
    "arvore": "tree",
    "folha": "leaf",
    "semente": "seed",
    "nuvem": "cloud",
    "estrela": "star",
    "lua": "moon",
    "sol": "sun",
    "marte": "mars planet",
    "saturno": "saturn planet",
    "jupiter": "jupiter planet",
    "mercurio": "mercury planet",
    "venus": "venus planet",
    "urano": "uranus planet",
    "netuno": "neptune planet",
    "plutao": "pluto planet",
    "galaxia": "galaxy",
    "cometa": "comet",
    "meteoro": "meteor",
    "asteroide": "asteroid",
    "planeta": "planet",
    "foguete": "rocket",
    "nave": "spacecraft",
    "buraco negro": "black hole",
    "via lactea": "milky way",
    "fogo": "fire",
    "agua": "water",
    "terra": "soil",
    "vento": "wind",
    "neve": "snow",
    "chuva": "rain",
}


def _wiki_get(url: str, params: dict | None = None) -> httpx.Response:
    try:
        response = httpx.get(
            url,
            params=params,
            headers=_WIKI_UA,
            timeout=_TIMEOUT,
            follow_redirects=True,
        )
        response.raise_for_status()
        return response
    except httpx.HTTPError as exc:
        raise RuntimeError(
            f"sem resposta do Wikimedia ({exc.__class__.__name__})"
        ) from exc


def _info_foto(titulo: str) -> dict | None:
    """URL pronta (miniatura grande) e nome limpo de um arquivo do Commons."""
    try:
        dados = _wiki_get(
            "https://api.wikimedia.org/core/v1/commons/file/"
            + urllib.parse.quote(titulo, safe="")
        ).json()
    except (RuntimeError, ValueError):
        return None
    preferida = dados.get("preferred") or {}
    url = str(preferida.get("url") or "")
    largura = int(preferida.get("width") or 0)
    if not url or largura < 500:
        return None
    caminho = url.split("?")[0].lower()
    if not caminho.endswith((".jpg", ".jpeg", ".png", ".webp")):
        return None
    nome = titulo[5:] if titulo.lower().startswith("file:") else titulo
    nome = re.sub(r"^lossy-page\d+-", "", nome, flags=re.I)
    nome = re.sub(r"\.(jpe?g|png|webp|gif|tiff?)$", "", nome, flags=re.I)
    nome = nome.replace("_", " ").strip()
    return {"url": url.split("?")[0], "titulo": nome[:120], "largura": largura}


def _titulos_wiki(consulta: str, limite: int) -> list[str]:
    """Títulos de arquivos do Commons para uma consulta (só imagens)."""
    try:
        dados = _wiki_get(
            "https://api.wikimedia.org/core/v1/commons/search/page",
            {"q": f"{consulta} filetype:bitmap", "limit": limite},
        ).json()
    except (RuntimeError, ValueError):
        return []
    return [
        str(pagina.get("title") or "")
        for pagina in dados.get("pages", [])
        if str(pagina.get("title") or "").lower().startswith("file:")
    ]


def _fotos_openverse(termo: str, quantidade: int) -> list[dict]:
    """Fotos do Openverse (busca de conteúdo, licença livre).

    É a fonte principal: busca por relevância de conteúdo e cobre Flickr CC,
    Unsplash, Wikimedia, NASA… Devolve ``[{"url","titulo","largura"}]``; lista
    vazia quando a rede/limite falha ou nada bom aparece (aí o Wikimedia cobre).
    """
    try:
        resposta = httpx.get(
            _OPENVERSE_URL,
            params={
                "q": termo,
                "page_size": min(20, max(4, quantidade * 3)),
                "mature": "false",
                "license_type": "all-cc",
            },
            headers=_WIKI_UA,
            timeout=_TIMEOUT,
            follow_redirects=True,
        )
        resposta.raise_for_status()
        resultados = resposta.json().get("results", [])
    except (httpx.HTTPError, ValueError) as exc:
        print(f"[fotos] Openverse indisponível: {type(exc).__name__}")
        return []

    achadas: list[dict] = []
    for item in resultados:
        if item.get("mature") or item.get("unstable__sensitivity"):
            continue
        url = str(item.get("url") or "")
        largura = int(item.get("width") or 0)
        titulo = str(item.get("title") or "").strip()
        if not url or largura < 600:
            continue
        if not url.split("?")[0].lower().endswith(
            (".jpg", ".jpeg", ".png", ".webp")
        ):
            continue
        if _FOTO_BLOQUEIO.search(titulo) or _FOTO_LIXO.search(titulo):
            continue
        achadas.append(
            {"url": url, "titulo": (titulo or "foto")[:120], "largura": largura}
        )
        if len(achadas) >= quantidade:
            break
    return achadas


def fotos(termo: str, quantidade: int = 6) -> list[dict]:
    """Fotos reais que combinam com o tema.

    Devolve ``[{"url", "titulo", "largura"}]``, em ordem de relevância.
    Lista vazia = nenhuma foto boa para o tema (o site deve usar SVG/CSS) —
    foto errada é pior do que foto nenhuma.

    Fontes: Openverse primeiro (busca de conteúdo) e Wikimedia Commons depois.
    """
    termo = (termo or "").strip()
    if not termo:
        return []
    # Adjetivo de categoria atrapalha: "animais raros" traz exposição de museu,
    # "flores bonitas" traz quadro. Tira o adjetivo e busca o substantivo.
    termo = re.sub(r"\s+", " ", _TEMA_ADJETIVO.sub(" ", termo)).strip()
    # Palavra de marketing não é assunto: pedir foto de "bem profissional",
    # "didático" ou "moderno" devolve propaganda/quadro aleatório. Se o tema
    # inteiro for só isso (sem um substantivo concreto), é melhor devolver nada
    # — o prompt manda ilustrar em SVG/CSS.
    sobra = [
        p
        for p in re.split(r"[^\wÀ-ÿ]+", _sem_acento(termo).lower())
        if p and p not in _TEMA_MARKETING and len(p) > 2
    ]
    if not sobra:
        return []
    # Só sobrou categoria vazia ("animais raros" -> "animais")? Devolver nada é
    # melhor que devolver fresco de igreja: o prompt manda a IA ilustrar em
    # SVG ou buscar por assunto concreto.
    if _sem_acento(termo).lower().strip() in _TEMA_CATEGORIA:
        return []
    quantidade = max(1, min(10, int(quantidade or 6)))

    def _tokens(texto: str) -> list[str]:
        """Palavras com conteúdo (tira artigo/preposição e ruído curto)."""
        return [
            _sem_acento(p).lower()
            for p in re.split(r"[^\wÀ-ÿ]+", _sem_acento(texto))
            if len(p) > 2
        ]

    # Monta as consultas na ordem certa para cada tipo de palavra.
    #
    # - Homônimo em português (_EM_INGLES): o termo em inglês resolve o
    #   sentido — "leão" acha "Carneiro Leão" (sobrenome) e "Fábrica Leão"
    #   (empresa), mas "lion" acha o animal.
    # - Palavra ambígua (_DESAMBIGUA): a expansão é OBRIGATÓRIA e vem primeiro.
    #   "academia" acha academia de letras e My Hero Academia; o título tem de
    #   trazer "musculação" para valer.
    # - Palavra que funciona sozinha (_SINONIMOS): o TERMO PEDIDO vem primeiro
    #   e o sinônimo só completa o que faltar.
    partes = termo.split()
    tema_norm = _sem_acento(termo)

    def _expandir(mapa: dict[str, str]) -> str:
        for chave_exp, extra in mapa.items():
            if re.search(rf"\b{re.escape(chave_exp)}\w*", tema_norm):
                resto = [
                    p
                    for p in partes
                    if not _sem_acento(p).startswith(chave_exp)
                ]
                return " ".join([extra, *resto]).strip()
        return ""

    em_ingles = _expandir(_EM_INGLES)
    desambiguada = _expandir(_DESAMBIGUA)
    sinonimizada = _expandir(_SINONIMOS)

    consultas: list[str] = []
    if em_ingles and em_ingles.lower() != termo.lower():
        consultas.append(em_ingles)
    if desambiguada and desambiguada.lower() != termo.lower():
        consultas.append(desambiguada)
    consultas.append(termo)
    if sinonimizada and sinonimizada.lower() != termo.lower():
        consultas.append(sinonimizada)
    if len(partes) > 2:
        consultas.append(" ".join(partes[:2]))
    if len(partes) > 1:
        consultas.append(partes[0])

    # Tokens que valem como "o tema" neste pedido: os do termo pedido e os das
    # expansões (inglês, desambiguação). Um título vale se casar com QUALQUER
    # um deles — senão a foto achada em inglês ("Lion male") seria jogada fora
    # por não conter a palavra em português ("leão").
    tokens_validos: list[str] = []
    for consulta in consultas:
        for token in _tokens(consulta):
            if token not in tokens_validos:
                tokens_validos.append(token)

    chave = termo.lower()
    if chave in _FOTOS_CACHE:
        guardadas = _FOTOS_CACHE[chave]
        # O cache é por tema, mas cada foto pode ter vindo de uma consulta
        # diferente. Revalida contra os tokens válidos: sem isso, um resultado
        # ruim cacheado por engano (um livro antigo) era servido como foto do
        # tema em todo pedido seguinte.
        guardadas = [
            item
            for item in guardadas
            if any(
                re.search(
                    rf"\b{re.escape(t)}\w*\b",
                    " ".join(_tokens(item["titulo"])),
                )
                for t in tokens_validos
            )
        ]
        if guardadas:
            return [dict(item) for item in guardadas[:quantidade]]
        _FOTOS_CACHE.pop(chave, None)

    # Fonte principal: Openverse. Busca por CONTEÚDO — "lua" acha a Lua e
    # "leão" acha o animal, sem depender do nome do arquivo. As consultas
    # (inglês, desambiguação, termo pedido, sinônimo) vão em PARALELO: a
    # primeira resposta de cada tema é lenta do lado deles (~5-10 s), e em
    # série isso virava meio minuto por site. Em paralelo, o site espera a
    # consulta mais lenta — e teto curto garante que nunca trava.
    abertas: list[dict] = []
    try:
        alvos = list(dict.fromkeys(consultas))[:4]
        with ThreadPoolExecutor(max_workers=len(alvos) or 1) as pool:
            futuros = [
                (consulta, pool.submit(_fotos_openverse, consulta, quantidade))
                for consulta in alvos
            ]
            for consulta, futuro in futuros:
                try:
                    itens = futuro.result(timeout=12)
                except Exception:  # noqa: BLE001 - uma consulta lenta não derruba
                    continue
                vistos = {item["url"] for item in abertas}
                for item in itens:
                    if item["url"] not in vistos:
                        vistos.add(item["url"])
                        abertas.append(item)
                if len(abertas) >= quantidade:
                    break
        if abertas:
            abertas = abertas[:quantidade]
            if len(_FOTOS_CACHE) >= _MAX_CACHE:
                _FOTOS_CACHE.pop(next(iter(_FOTOS_CACHE)))
            _FOTOS_CACHE[chave] = [dict(item) for item in abertas]
            print(f"[fotos] {len(abertas)} do Openverse para «{termo}»")
            return abertas
    except Exception as exc:  # noqa: BLE001 - Openverse é bônus, nunca derruba
        print(f"[fotos] Openverse falhou: {exc}")
        abertas = []

    # Um título só é aceito se casar com os tokens da CONSULTA que o trouxe,
    # e a nota vale posição: o tema no COMEÇO do título é foto do tema ("Taki
    # Pizzaria"), o tema enterrado no fim é paisagem com o tema ao fundo
    # ("Headquarters of Greenlandic newspaper … next to the pizzaria").
    def nota(titulo: str, alvo_tokens: list[str]) -> int:
        palavras = _tokens(titulo)
        pontos = 0
        for token in alvo_tokens:
            for i, palavra in enumerate(palavras):
                if re.match(rf"{re.escape(token)}\w*$", palavra):
                    pontos += max(1, 8 - min(i, 7))
                    break
        return pontos

    candidatos: list[str] = []
    for consulta in consultas:
        consulta_tokens = _tokens(consulta)
        if not consulta_tokens:
            continue
        achados: list[tuple[int, str]] = []
        for titulo in _titulos_wiki(consulta, max(12, quantidade * 3)):
            if _FOTO_BLOQUEIO.search(titulo) or _FOTO_LIXO.search(titulo):
                continue
            p = nota(titulo, consulta_tokens)
            if p > 0:
                achados.append((p, titulo))
        achados.sort(key=lambda par: par[0], reverse=True)
        for _p, titulo in achados:
            if titulo not in candidatos:
                candidatos.append(titulo)
        if len(candidatos) >= quantidade:
            break

    if not candidatos:
        # Tenta Unsplash se não achou nada
        pass

    achadas: list[dict] = []
    vistos_ok: set[str] = set()
    if candidatos:
        # Cada candidato custa uma requisição de detalhe; em paralelo é rápido.
        with ThreadPoolExecutor(max_workers=6) as pool:
            for item in pool.map(_info_foto, candidatos):
                if (
                    not item
                    or _FOTO_BLOQUEIO.search(item["titulo"])
                    or _FOTO_LIXO.search(item["titulo"])
                ):
                    continue
                assinatura = item["titulo"].lower()
                if assinatura in vistos_ok:
                    continue
                vistos_ok.add(assinatura)
                achadas.append(item)
                if len(achadas) >= quantidade:
                    break

    # Junta: Openverse primeiro (busca de conteúdo), Wikimedia completando.
    todas = list(abertas)
    urls_vistas = {item["url"] for item in todas}
    for item in achadas:
        if item["url"] not in urls_vistas and len(todas) < quantidade:
            urls_vistas.add(item["url"])
            todas.append(item)

    # Unsplash (opcional) — muito bom pra foto EXATA por item (nome do prato/animal)
    key_unsplash = os.getenv("UNSPLASH_ACCESS_KEY") or os.getenv("UNSPLASH_KEY")
    if key_unsplash and len(todas) < quantidade:
        try:
            resp = httpx.get(
                _UNSPLASH_URL,
                params={"query": termo, "per_page": min(30, max(10, quantidade * 4)), "orientation": "landscape"},
                headers={"Authorization": f"Client-ID {key_unsplash}", "Accept-Version": "v1"},
                timeout=_TIMEOUT,
                follow_redirects=True,
            )
            if resp.status_code == 200:
                data = resp.json()
                for res in data.get("results", []):
                    urls = res.get("urls") or {}
                    url = urls.get("regular") or urls.get("small") or urls.get("full")
                    if not url:
                        continue
                    if url in urls_vistas:
                        continue
                    user = (res.get("user") or {}).get("name") or "Unsplash"
                    alt = res.get("alt_description") or res.get("description") or termo
                    titulo = f"{alt} — Foto: {user} / Unsplash"
                    urls_vistas.add(url)
                    todas.append({"url": url, "titulo": titulo[:140], "largura": int(res.get("width") or 0)})
                    if len(todas) >= quantidade:
                        break
                if todas:
                    print(f"[fotos] {len(todas)} com Unsplash/Openverse/Wikimedia para «{termo}»")
        except Exception as exc:  # noqa: BLE001
            print(f"[fotos] Unsplash indisponível: {exc}")

    if not todas:
        return []
    if len(_FOTOS_CACHE) >= _MAX_CACHE:
        _FOTOS_CACHE.pop(next(iter(_FOTOS_CACHE)))
    _FOTOS_CACHE[chave] = [dict(item) for item in todas]
    return todas[:quantidade]


def imagens(termo: str, quantidade: int = 6) -> str:
    """Versão em texto (para a ferramenta do agente)."""
    itens = fotos(termo, quantidade)
    if not itens:
        return (
            f"Sem fotos para «{termo}» nesta busca. Tente um termo mais simples e "
            "concreto (o substantivo do produto/lugar/bicho, sem adjetivo). Foto "
            "real é o que o cliente espera: só caia para SVG/CSS se, mesmo com o "
            "termo simples, não houver foto — e nunca invente URL de imagem."
        )
    linhas = [f"Fotos reais para «{termo}» (uso livre):"]
    linhas.extend(
        f"{i}. {item['url']} — {item['titulo']}" for i, item in enumerate(itens, 1)
    )
    linhas.append(
        "Use estas URLs em <img>, com alt descritivo em português — cada foto no "
        "bloco do assunto dela. Prefira a foto real; só use SVG/CSS para um item "
        "que não combine com nenhuma delas."
    )
    return _clip("\n".join(linhas))


def prefetch(termos: list[str]) -> None:
    """Aquece o cache de fotos sem travar quem chamou (fire-and-forget).

    A Openverse demora ~9 s na PRIMEIRA consulta de cada termo (cache frio do
    lado deles) e ~0,02 s nas seguintes. Se o agente buscar "leão" só na hora
    de escrever o HTML, o site inteiro espera esses 9 s — por termo. Aquecer em
    paralelo, assim que o pedido de site chega, faz a ferramenta `imagens`
    acertar o cache e responder na hora.

    Roda em thread separada e engole qualquer erro: pré-aquecimento é bônus e
    nunca pode atrapalhar a resposta principal.
    """
    limpos = [t.strip() for t in termos if t and t.strip()]
    limpos = list(dict.fromkeys(limpos))[:6]
    if not limpos:
        return

    def _aquecer() -> None:
        try:
            with ThreadPoolExecutor(max_workers=len(limpos)) as pool:
                list(pool.map(lambda t: fotos(t, 6), limpos))
        except Exception:  # noqa: BLE001 - bônus puro, nunca propaga
            pass

    ThreadPoolExecutor(max_workers=1).submit(_aquecer)
