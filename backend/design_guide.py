"""Biblioteca de design de agência para a Nébula.

Duas peças:

1. PLAYBOOK — um manual curtido (em pt-BR) que entra em TODO pedido de
   site/página/app. É o que faz a saída parecer feita por uma agência de
   verdade em vez de "site genérico de IA".
2. buscar()/ler() — acesso sob demanda aos 320+ agentes especialistas
   (design, marketing, engenharia, estratégia...) guardados em guias/.
   Assim tudo fica disponível sem inchar o prompt de cada resposta.

O conteúdo do playbook foi destilado dos agentes mais relevantes:
UI Designer, UX Architect, UI Finish-Gate Reviewer, Brand Guardian,
Visual Storyteller, Whimsy Injector, Persona Walkthrough, SEO Specialist
e Frontend Developer.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

GUIAS_DIR = Path(__file__).parent / "guias"

# ---------------------------------------------------------------- playbook

PLAYBOOK = (
    "\n\nMANUAL DE AGÊNCIA (siga à risca; é o que separa site profissional de rascunho):\n"

    "\nA) CONTRATO DE DESIGN — resolva em silêncio ANTES de escrever código:\n"
    "   - Usuário + tarefa: quem entra e o que essa pessoa precisa terminar/decidir.\n"
    "   - Objeto de primeira leitura: o que o olho deve achar em 1 segundo.\n"
    "   - Ação primária: UMA ação principal (o CTA que domina a página).\n"
    "   - Densidade: compacta, equilibrada ou espaçosa — e por quê.\n"
    "   - Hierarquia: título, sinal-chave, controles, informação de apoio.\n"
    "   - Prioridade responsiva: o que fica fixo, o que colapsa, o que muda de ordem.\n"
    "   - Defaults proibidos: os clichês que fariam este site servir para qualquer negócio.\n"

    "\nB) IDENTIDADE (sistema, não decoração):\n"
    "   - Cor: 1 primária + 1 acento + neutros (50→900) + semânticas (sucesso/erro/aviso),\n"
    "     tudo em variáveis :root. Contraste texto/fundo ≥ 4.5:1 (títulos grandes ≥ 3:1).\n"
    "   - Tipografia: par display+corpo ou system-ui (modo off); escala fluida com clamp()\n"
    "     (ex.: hero clamp(2.2rem,5vw,4rem)); line-height 1.1-1.25 em títulos e 1.5-1.7 no\n"
    "     corpo; tracking -0.02em em títulos grandes; medida de leitura 60-70ch.\n"
    "   - Espaçamento base 4/8px, ritmo vertical generoso entre seções (64-128px).\n"
    "   - Raios e sombras em escala pequena (--raio-sm/md/lg), sombras sutis e em camadas.\n"
    "   - Modo escuro: prefers-color-scheme + botão de tema (localStorage), cores por variáveis.\n"
    "   - Logo: wordmark simples em SVG/CSS, coerente com a paleta (não precisa imagem).\n"

    "\nC) COMPONENTES E ESTADOS (o que denuncia amadorismo é a falta deles):\n"
    "   - Todo interativo tem: default, hover, active, focus-visible (anel visível), disabled,\n"
    "     carregando, vazio e erro. NUNCA botão sem hover/focus.\n"
    "   - Formulários: label visível (não só placeholder), validação clara, erro gentil,\n"
    "     estado de sucesso; botão desabilitado enquanto envia.\n"
    "   - Feedback: skeleton/spinner ao carregar; empty state que explica e sugere ação.\n"
    "   - Consistência: mesmo raio, sombra, transição e espaçamento em tudo.\n"

    "\nD) LAYOUT E RESPONSIVO:\n"
    "   - Container central (max-width ~72-80rem) com padding lateral fluido.\n"
    "   - Cards com CSS Grid auto-fit/minmax (mín. 260-320px); nada de largura fixa que estoura.\n"
    "   - Mobile-first real: 360 → 768 → 1024 → 1440px. Em 360px nada rola na horizontal,\n"
    "     alvos de toque ≥ 44px, nav vira menu.\n"
    "   - Primeira dobra: hero com eyebrow + título de benefício + subtítulo + 2 CTAs (um\n"
    "     primário forte) + prova visual. Tem que parecer site de verdade já na dobra.\n"
    "   - Seções com respiro e hierarquia (evite 4 cards idênticos disputando atenção).\n"
    "     Rodapé completo: contato, links, redes, aviso legal quando couber.\n"
    "   - Movimento: transições 150-220ms com cubic-bezier suave, reveal-on-scroll discreto,\n"
    "     hover com leve elevação. NADA de animação infinita chamativa. Respeite\n"
    "     prefers-reduced-motion.\n"

    "\nE) ACESSIBILIDADE (obrigatório):\n"
    "   - HTML semântico (header/nav/main/section/article/footer), UM h1, h2/h3 em ordem.\n"
    "   - Toda <img> com alt descritivo em pt-BR; decorativa com alt=\"\".\n"
    "   - Teclado 100% funcional, foco visível, ordem de tabulação lógica.\n"
    "   - ARIA só quando o HTML nativo não resolve (aria-expanded no menu, aria-current no link).\n"
    "   - Legível com zoom de 200%; nunca texto essencial dentro de imagem.\n"

    "\nF) COPY E CONVERSÃO:\n"
    "   - Headline = benefício concreto, nunca \"Bem-vindo\" nem adjetivo vazio.\n"
    "   - LIFT: Relevância (fala com quem chegou), Clareza (entende em 5s), Urgência (por que\n"
    "     agora), menos Ansiedade (quebre objeções), menos Distração (um caminho principal).\n"
    "   - Cialdini: prova social (depoimentos com nome/resultado), autoridade (números, anos,\n"
    "     certificações, parceiros), reciprocidade (valor grátis), escassez real, afinidade\n"
    "     (tom humano, \"você\").\n"
    "   - Fogg: CTA longe → aproxime; ninguém convencido → mais prova; tudo pronto → um lembrete.\n"
    "   - PT-BR impecável e natural, zero lorem ipsum, zero clichê (\"soluções inovadoras\").\n"
    "     Números plausíveis e coerentes entre seções. Microcopy humana em erro/vazio/loading.\n"

    "\nG) IMAGENS (regra de ouro: foto certa ou nenhuma):\n"
    "   - Use SOMENTE URLs da lista FOTOS REAIS; nunca invente link nem placehold.co/picsum.\n"
    "   - Cada foto na seção certa e coerente com o texto; nunca repetir a mesma foto.\n"
    "   - <img> com alt real, loading=\"lazy\", width/height (evita CLS) e object-fit:cover.\n"
    "   - Texto sobre foto pede overlay escuro + corte/variação de enquadramento.\n"
    "   - Sem foto boa? Resolva com CSS/SVG rico (gradiente, padrão, ilustração) — feio não.\n"

    "\nH) SEO E PERFORMANCE:\n"
    "   - <title> e meta description únicos com o termo principal; uma h1 só; lang=\"pt-BR\".\n"
    "   - Open Graph (og:title/description/image) e, quando fizer sentido, JSON-LD do negócio\n"
    "     (LocalBusiness/Restaurant/...) com endereço/telefone/horário coerentes com a página.\n"
    "   - Core Web Vitals: LCP < 2,5s, INP < 200ms, CLS < 0,1. Adie JS, dimensione imagens.\n"

    "\nI) FINISH GATE — reprove e corrija antes de entregar se houver:\n"
    "   - \"Dashboard/blocos genéricos\" que serviriam para qualquer empresa.\n"
    "   - Gradiente decorativo roxo-azul centralizado + dois botões iguais.\n"
    "   - Grade de cards sem hierarquia, ícone de biblioteca sem propósito, \"moderno\" sem razão.\n"
    "   - Trocar o nome e o site servir para outro negócio qualquer (isso reprova).\n"
    "   PASS só quando: o negócio se entende na primeira dobra, a ação principal é óbvia,\n"
    "   os estados existem e nada é intercambiável.\n"
)


# ------------------------------------------------------- biblioteca sob demanda

# Nome amigável de cada divisão (para o modelo escolher a área).
AREA_LABELS = {
    "design": "design (UI/UX, marca, imagens, storytelling)",
    "engineering": "engenharia (frontend, backend, dados, DevOps)",
    "marketing": "marketing (copy, SEO, redes, growth)",
    "product": "produto (estratégia, roadmap, métricas)",
    "strategy": "estratégia (negócio, posicionamento)",
    "sales": "vendas",
    "finance": "finanças",
    "testing": "testes e QA",
    "security": "segurança",
    "healthcare": "saúde",
    "academic": "acadêmico/pesquisa",
    "game-development": "jogos",
    "gis": "geoprocessamento",
    "integrations": "integrações",
    "paid-media": "mídia paga/anúncios",
    "project-management": "gestão de projetos",
    "research": "pesquisa",
    "spatial-computing": "computação espacial/AR-VR",
    "specialized": "especialistas diversos",
    "support": "suporte ao cliente",
}

# A biblioteca é em inglês; essas pontes ajudam a achar por termo em pt-BR.
_SINONIMOS = {
    "marca": ["brand", "branding"],
    "marcas": ["brand", "branding"],
    "identidade": ["brand", "identity"],
    "cor": ["color"],
    "cores": ["color"],
    "tipografia": ["typography", "font"],
    "fonte": ["font", "typography"],
    "texto": ["copy", "content", "writing"],
    "copy": ["copywriting", "content"],
    "escrita": ["writing", "copy"],
    "conversao": ["conversion", "cro", "landing"],
    "conversão": ["conversion", "cro", "landing"],
    "vendas": ["sales"],
    "seo": ["seo", "search"],
    "anuncio": ["ads", "paid", "media"],
    "anuncios": ["ads", "paid", "media"],
    "site": ["web", "website", "frontend"],
    "pagina": ["page", "landing"],
    "página": ["page", "landing"],
    "landing": ["landing", "conversion"],
    "acessibilidade": ["accessibility", "a11y", "inclusive"],
    "responsivo": ["responsive", "mobile"],
    "mobile": ["mobile", "responsive"],
    "imagem": ["image", "visual", "photo"],
    "imagens": ["image", "visual", "photo"],
    "foto": ["photo", "photography", "image"],
    "fotos": ["photo", "photography", "image"],
    "fotografia": ["photography", "photo"],
    "logo": ["logo", "brand"],
    "motion": ["motion", "animation"],
    "animacao": ["animation", "motion"],
    "animação": ["animation", "motion"],
    "teste": ["test", "testing", "qa"],
    "testes": ["test", "testing", "qa"],
    "seguranca": ["security"],
    "segurança": ["security"],
    "dados": ["data", "analytics"],
    "produto": ["product"],
    "preco": ["pricing"],
    "preço": ["pricing"],
    "email": ["email"],
    "social": ["social", "media"],
    "jogo": ["game"],
    "jogos": ["game"],
    "pesquisa": ["research"],
    "frontend": ["frontend"],
    "backend": ["backend"],
}

_INDEX: list[dict] | None = None


def _norm(text: str) -> str:
    """Minúsculas sem acento, para casar 'portfólio' com 'portfolio'."""
    flat = unicodedata.normalize("NFKD", text or "")
    flat = "".join(c for c in flat if not unicodedata.combining(c))
    return flat.lower()


def _frontmatter(text: str) -> tuple[str, str]:
    """Extrai (name, description) do cabeçalho YAML do agente."""
    name = desc = ""
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    if not match:
        return name, desc
    for line in match.group(1).splitlines():
        if line.startswith("name:"):
            name = line.split(":", 1)[1].strip().strip('"')
        elif line.startswith("description:"):
            desc = line.split(":", 1)[1].strip().strip('"')
    return name, desc


def _build_index() -> list[dict]:
    """Varre guias/ uma vez e guarda nome/descrição/divisão de cada agente."""
    items: list[dict] = []
    if not GUIAS_DIR.is_dir():
        return items
    for path in sorted(GUIAS_DIR.rglob("*.md")):
        rel = path.relative_to(GUIAS_DIR)
        division = rel.parts[0] if len(rel.parts) > 1 else ""
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        name, desc = _frontmatter(text)
        if not name:
            name = path.stem.replace("-", " ").title()
        items.append(
            {
                "file": str(rel),
                "division": division,
                "name": name,
                "desc": desc,
                "haystack": _norm(f"{name} {desc} {rel} {division}"),
            }
        )
    return items


def _index() -> list[dict]:
    global _INDEX
    if _INDEX is None:
        _INDEX = _build_index()
    return _INDEX


def listar() -> str:
    """Resumo da biblioteca: quantos agentes por divisão."""
    itens = _index()
    if not itens:
        return "A biblioteca de guias ainda não foi instalada."
    contagem: dict[str, int] = {}
    for item in itens:
        contagem[item["division"] or "raiz"] = contagem.get(item["division"] or "raiz", 0) + 1
    linhas = [
        f"- {div}: {n} agentes — {AREA_LABELS.get(div, div)}"
        for div, n in sorted(contagem.items())
    ]
    return "Biblioteca de agentes especialistas (guias/):\n" + "\n".join(linhas)


def buscar(termo: str, limite: int = 5) -> str:
    """Procura agentes por assunto e devolve os mais próximos + como abrir."""
    itens = _index()
    if not itens:
        return "Biblioteca de guias indisponível."
    palavras = [p for p in _norm(termo).split() if len(p) > 2]
    if not palavras:
        return "Diga o assunto (ex.: 'design system', 'copywriting', 'seo local')."

    # amplia cada palavra com sinônimos (pt→en), sem repetir.
    termos: list[str] = []
    for palavra in palavras:
        termos.append(palavra)
        for sin in _SINONIMOS.get(palavra, []):
            if sin not in termos:
                termos.append(sin)

    pontuados: list[tuple[int, dict]] = []
    for item in itens:
        score = 0
        hay = item["haystack"]
        nome = _norm(item["name"])
        for palavra in termos:
            if palavra in nome:
                score += 6
            elif palavra in hay:
                score += 3
        if score:
            if _norm(termo) in hay:
                score += 4
            pontuados.append((score, item))

    pontuados.sort(key=lambda par: (-par[0], par[1]["file"]))
    if not pontuados:
        return (
            "Nenhum agente casou direto. Tente uma palavra mais simples "
            "(ex.: 'design', 'copy', 'seo', 'marca', 'landing')."
        )
    linhas = []
    for score, item in pontuados[:limite]:
        linhas.append(f"- {item['name']} [{item['division']}] -> {item['file']}\n  {item['desc'][:180]}")
    return (
        "Agentes mais relevantes (use `ler` com o caminho da seta):\n" + "\n".join(linhas)
    )


def ler(caminho: str) -> str:
    """Devolve o conteúdo de um guia pelo nome do arquivo ou nome do agente."""
    itens = _index()
    alvo = _norm(caminho).strip()
    if not alvo:
        return "Diga qual guia abrir (ex.: 'design-ui-designer')."

    escolhido = None
    for item in itens:
        if alvo in _norm(item["file"]) or alvo == _norm(item["name"]):
            escolhido = item
            break
    if escolhido is None:
        # segunda tentativa: por palavras soltas
        palavras = [p for p in alvo.split() if len(p) > 2]
        for item in itens:
            nome = _norm(item["name"]) + " " + _norm(item["file"])
            if palavras and all(p in nome for p in palavras):
                escolhido = item
                break
    if escolhido is None:
        return buscar(caminho, limite=5)

    path = GUIAS_DIR / escolhido["file"]
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return f"não consegui abrir {escolhido['file']}: {exc}"
    # tira o cabeçalho YAML (não ajuda o modelo) e limita o tamanho.
    corpo = re.sub(r"^---\s*\n.*?\n---\s*\n", "", text, count=1, flags=re.S).strip()
    return f"# {escolhido['name']} ({escolhido['division']})\n\n{corpo[:12000]}"
