"""Planejamento antes de criar: perguntas afiadas por tipo de projeto.

Por que existe: o erro mais comum ao criar site/app é o desalinhamento. O
usuário pede "um site pra minha loja" e a IA supõe cor, tom, seções, preço…
e entrega algo que não era o que ele queria. A correção é perguntar ANTES.

Esta é a versão para o usuário final (não-programador) da ideia de "grilling":
em vez de a IA sair fazendo, ela faz de 3 a 6 perguntas certeiras, agrupadas,
e só depois cria. O objetivo é reduzir retrabalho e acerto na primeira.
"""

import re

# Perguntas que valem para QUALQUER projeto (o básico que sempre muda o
# resultado e quase nunca vem no pedido).
_BASE = [
    "Qual é o nome do negócio/projeto e o que ele faz em uma frase?",
    "Quem é o público (quem você quer que visite/usem)?",
    "Qual ação você quer que a pessoa faça (chamar no WhatsApp, comprar, "
    "agendar, ver o portfólio, só conhecer)?",
    "Tem cores, logo ou referência de estilo que você gosta? (pode mandar "
    "um link ou dizer 'algo parecido com…')",
]

# Perguntas específicas por tipo. Só entram as que fazem sentido para o tipo.
_POR_TIPO: dict[str, list[str]] = {
    "site": [
        "Quais seções você quer? (ex.: início, sobre, serviços, galeria, "
        "depoimentos, contato)",
        "Você já tem os textos e fotos, ou quer que eu escreva/monte o conteúdo?",
    ],
    "app": [
        "O que o app faz, passo a passo, do ponto de vista de quem usa?",
        "Ele precisa guardar dados (login, histórico, cadastro) ou é só tela?",
        "Onde vai rodar: celular (Android/iPhone), computador ou navegador?",
    ],
    "loja": [
        "Quantos produtos mais ou menos e quais categorias?",
        "A compra fecha no site (carrinho/pagamento) ou é pedido por WhatsApp?",
        "Como calcula o frete/entrega e quais formas de pagamento aceita?",
    ],
    "portfolio": [
        "Que trabalhos quer mostrar (quantos e de que área)?",
        "Quer uma página só, ou uma por projeto?",
        "Quer destacar currículo/serviços para contratantes?",
    ],
    "landing": [
        "Qual é a oferta principal e o preço/condição (se for mostrar)?",
        "Que objeções do cliente a página precisa responder? "
        "(ex.: 'é caro', 'funciona mesmo?')",
        "Tem depoimento, número ou resultado que sirva de prova social?",
    ],
    "blog": [
        "Sobre o que você escreve e com que frequência?",
        "Quer categorias/tags ou uma lista simples de posts?",
        "Vai ter comentários ou só leitura?",
    ],
    "outro": [
        "Me conta em detalhes o que você imagina, como se estivesse explicando "
        "para um amigo.",
        "O que NÃO pode faltar de jeito nenhum?",
    ],
}

# Sinônimos que o modelo pode mandar como "tipo" e a que tipo real pertencem.
_ALIAS = {
    "website": "site",
    "página": "site",
    "pagina": "site",
    "páginas": "site",
    "ecommerce": "loja",
    "e-commerce": "loja",
    "loja virtual": "loja",
    "marketplace": "loja",
    "cardápio": "site",
    "cardapio": "site",
    "portfólio": "portfolio",
    "portifolio": "portfolio",
    "one-page": "landing",
    "onepage": "landing",
    "página de vendas": "landing",
    "pagina de vendas": "landing",
}


def _tipo_normalizado(tipo: str) -> str:
    chave = (tipo or "").strip().lower()
    chave = _ALIAS.get(chave, chave)
    return chave if chave in _POR_TIPO else "outro"


def perguntas(tipo: str = "outro", assunto: str = "") -> str:
    """Texto pronto (para a ferramenta do agente) com as perguntas a fazer.

    Devolve instruções curtas + as perguntas certas para o tipo. O agente lê
    isso e faz ao usuário — não cria nada ainda.
    """
    tipo_real = _tipo_normalizado(tipo)
    tema = (assunto or "").strip()
    especificas = _POR_TIPO.get(tipo_real, _POR_TIPO["outro"])
    # Teto de 6 perguntas no total: pergunta demais cansa e o usuário desiste.
    # As específicas entram primeiro (são o que muda o resultado), a base
    # completa até o limite.
    todas = (especificas + _BASE)[:6]

    linhas = [
        "PLANEJAR ANTES DE CRIAR — não gere o projeto nesta resposta ainda.",
        "",
        "Fale com o usuário em português, tom natural e direto (nada de "
        "formulário robótico). Agrupe as perguntas abaixo em uma única "
        "mensagem curta, numeradas, e diga que assim que ele responder você "
        "já faz a primeira versão.",
        "",
        "Regras desta etapa:",
        "- Não invente resposta no lugar dele; pergunte o que falta.",
        "- Se algo já veio no pedido, NÃO pergunte de novo — só o que falta.",
        "- No máximo 6 perguntas. Se o pedido já estiver bem detalhado, "
        "pergunte só 1 ou 2 pontos realmente críticos — ou nenhum, e vá criar.",
    ]
    if tema:
        linhas.append(f"- Contexto já conhecido: {tema[:200]}.")
    linhas.append("")
    linhas.append(f"Perguntas recomendadas para um projeto do tipo «{tipo_real}»:")
    for i, pergunta in enumerate(todas, 1):
        linhas.append(f"{i}. {pergunta}")
    return "\n".join(linhas)


# --------------------------------------------------- forçar por código

# Detalhe que, se o pedido já trouxer, dispensa a entrevista: cor, seção,
# preço, público, contato, estilo. Sem nenhum disso, o pedido é "vago".
_JA_TEM_DETALHE = re.compile(
    r"(?i)\b(azul|vermelh[oa]|verde|preto|branc[oa]|roxo|rosa|dourad[oa]|"
    r"laranja|amarel[oa]|bege|cinza|gradiente|escuro|claro|"
    r"in[íi]cio|sobre|servi[çc]os?|galeria|depoimentos?|contato|card[áa]pio|"
    r"menu|se[çc][õo]es?|banner|rodap[ée]|pre[çc]os?|planos?|"
    r"whatsapp|telefone|endere[çc]o|e-?mail|instagram|"
    r"moderno|minimalista|elegante|cl[áa]ssico|jovem|infantil|"
    r"loja\s+de|est[úu]dio|academia|padaria|barbearia)\b"
)
# Um pedido muito longo já traz contexto; um curto é vago.
_VAGO_MAX_CHARS = 120


def deve_perguntar(message: str) -> bool:
    """True quando vale PARAR e perguntar antes de criar (forçado por código).

    Regra: pedido de criar site/página/app/loja + curto + sem nenhum detalhe
    concreto (cor, seção, preço, contato, tipo de negócio) = vago. Nesse caso
    a Nébula pergunta, em vez de criar às cegas.

    NÃO pergunta quando: o pedido é longo/detalhado, ou é ajuste de algo que
    já existe na conversa (aí a intenção já está clara).
    """
    texto = (message or "").strip()
    if not texto:
        return False
    if len(texto) > _VAGO_MAX_CHARS:
        return False
    if not _PEDIDO_CRIAR.search(texto):
        return False
    if _JA_TEM_DETALHE.search(texto):
        return False
    if _AJUSTE.search(texto):
        return False
    return True


# "faz/faça/cria/crie/monta/quero/preciso ... site/página/app/loja/..."
_PEDIDO_CRIAR = re.compile(
    r"(?i)(\b(fa[çc]a|faz|fazer|cri[ae]|criar|mont[ae]|montar|quero|queria|"
    r"preciso|gostaria|desenvolv[ae])\b.{0,40}?"
    r"\b(site|sites|p[áa]gina|p[áa]ginas|landing|website|app|aplicativ\w+|"
    r"loja|portf[óo]lio|blog|e-?commerce|card[áa]pio)\b)"
)
# Ajuste numa página que já existe: aí a conversa já tem o contexto.
_AJUSTE = re.compile(
    r"(?i)\b(mud[ae]|troc[ae]|alter[ae]|atualiz\w*|melhor\w*|corrig\w*|"
    r"ajust\w*|adicion\w*|acrescent\w*|inclu\w*|coloque|colocar|p[õo]e|"
    r"refa[çz]\w*|remove|remover|apag\w*)\b"
)


def tipo_do_pedido(message: str) -> str:
    """Deduz o tipo de projeto pelo texto, para escolher as perguntas."""
    texto = _sem_acento_simples((message or "").lower())
    if re.search(r"\b(app|aplicativ\w*)", texto):
        return "app"
    if re.search(r"\b(loja|e-?commerce|marketplace)", texto):
        return "loja"
    if re.search(r"\b(portf[óo]lio|portfolio)", texto):
        return "portfolio"
    if re.search(r"\b(landing|p[áa]gina de vendas)", texto):
        return "landing"
    if re.search(r"\b(blog)", texto):
        return "blog"
    return "site"


def _sem_acento_simples(texto: str) -> str:
    import unicodedata

    bruto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in bruto if unicodedata.category(c) != "Mn")


def resposta_ao_usuario(message: str) -> str:
    """Mensagem PRONTA que a Nébula devolve quando o pedido é vago.

    Sai direto para o usuário (sem passar pelo modelo), então é determinístico:
    pedido vago sempre recebe as perguntas. Depois que ele responder, a próxima
    mensagem já traz detalhes e a criação acontece normalmente.
    """
    tipo = tipo_do_pedido(message)
    tipo_real = _tipo_normalizado(tipo)
    especificas = _POR_TIPO.get(tipo_real, _POR_TIPO["outro"])
    todas = (especificas + _BASE)[:4]
    linhas = [
        "Boa! Antes de eu montar, me responde essas rapidinho pra eu acertar de "
        "primeira (pode responder tudo em uma mensagem só):",
        "",
    ]
    for i, pergunta in enumerate(todas, 1):
        linhas.append(f"{i}. {pergunta}")
    linhas.append("")
    linhas.append(
        "Se preferir, responde só o que quiser e eu já começo com o resto no "
        "padrão."
    )
    return "\n".join(linhas)
