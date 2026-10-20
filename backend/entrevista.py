"""Entrevista interativa antes de criar: etapas com opções clicáveis.

Por que existe: pedir ao usuário que digite tudo ("quais seções? quais cores?
qual ação?") cansa e ele responde mal. Aqui a Nébula pergunta UMA etapa por
vez, com opções prontas pra tocar/ clicar — escolha única quando só cabe uma
(estilo, ação principal) e múltipla quando faz sentido juntar (seções, cores).

Roda 100% por código: não chama o Gemini. Então funciona sempre, responde na
hora e não gasta cota.

O tipo de projeto decide as etapas: site, app, loja, portfólio, landing, blog.
"""

from __future__ import annotations

# Cada etapa: id, pergunta, opções, e se aceita marcar mais de uma.
# "multi" = pode escolher várias; sem ele, escolhe uma só.
# "livre" = além das opções, o usuário pode digitar algo próprio.
_ETAPAS: dict[str, list[dict]] = {
    "site": [
        {
            "id": "tipo",
            "pergunta": "Que tipo de site é?",
            "multi": False,
            "opcoes": [
                "Negócio local (loja, salão, restaurante)",
                "Serviços (consultoria, obra, assistência)",
                "Institucional (empresa, ONG, igreja)",
                "Evento (casamento, festa, congresso)",
                "Outro",
            ],
        },
        {
            "id": "secoes",
            "pergunta": "Quais seções o site deve ter? (pode marcar várias)",
            "multi": True,
            "opcoes": [
                "Início",
                "Sobre",
                "Serviços/Produtos",
                "Galeria de fotos",
                "Depoimentos",
                "Preços/Tabela",
                "Perguntas frequentes",
                "Contato",
                "Localização/Mapa",
            ],
        },
        {
            "id": "acao",
            "pergunta": "Qual é a ação principal que o visitante deve fazer?",
            "multi": False,
            "opcoes": [
                "Chamar no WhatsApp",
                "Ligar por telefone",
                "Preencher formulário",
                "Ver no Instagram",
                "Comprar agora",
                "Só conhecer o negócio",
            ],
        },
        {
            "id": "estilo",
            "pergunta": "Qual estilo visual você prefere?",
            "multi": False,
            "opcoes": [
                "Moderno e limpo",
                "Elegante e sofisticado",
                "Colorido e divertido",
                "Rústico e aconchegante",
                "Minimalista",
                "Ousado e chamativo",
            ],
        },
        {
            "id": "cores",
            "pergunta": "Quais cores combinam com a marca? (pode marcar várias)",
            "multi": True,
            "opcoes": [
                "Vermelho",
                "Laranja",
                "Amarelo",
                "Verde",
                "Azul",
                "Roxo",
                "Rosa",
                "Marrom",
                "Preto e branco",
            ],
        },
        {
            "id": "conteudo",
            "pergunta": "Os textos e fotos, como fazemos?",
            "multi": False,
            "opcoes": [
                "Escreva os textos e busque as fotos por mim",
                "Eu mando os textos e fotos depois",
                "Mistura: você escreve e eu ajusto",
            ],
        },
    ],
    "app": [
        {
            "id": "funcao",
            "pergunta": "O que o app faz?",
            "multi": True,
            "opcoes": [
                "Lista/agenda de itens",
                "Calculadora ou ferramenta",
                "Catálogo de produtos",
                "Anotações/lembretes",
                "Chat ou mensagens",
                "Jogo simples",
                "Outro",
            ],
        },
        {
            "id": "dados",
            "pergunta": "Precisa guardar dados do usuário?",
            "multi": False,
            "opcoes": [
                "Sim, com login e cadastro",
                "Sim, mas só no aparelho (sem login)",
                "Não, é só tela",
            ],
        },
        {
            "id": "plataforma",
            "pergunta": "Onde o app vai rodar?",
            "multi": False,
            "opcoes": [
                "Celular Android",
                "Celular iPhone",
                "Navegador (roda em qualquer aparelho)",
                "Computador",
            ],
        },
        {
            "id": "estilo",
            "pergunta": "Qual estilo visual você prefere?",
            "multi": False,
            "opcoes": [
                "Moderno e limpo",
                "Colorido e divertido",
                "Sério e profissional",
                "Minimalista e escuro",
            ],
        },
        {
            "id": "cores",
            "pergunta": "Quais cores combinam com a marca? (pode marcar várias)",
            "multi": True,
            "opcoes": [
                "Azul",
                "Verde",
                "Roxo",
                "Laranja",
                "Vermelho",
                "Preto e branco",
            ],
        },
    ],
    "loja": [
        {
            "id": "produtos",
            "pergunta": "Que tipo de produto você vende?",
            "multi": True,
            "opcoes": [
                "Roupas e acessórios",
                "Comida e bebida",
                "Cosméticos/beleza",
                "Eletrônicos",
                "Casa e decoração",
                "Artesanato",
                "Serviços",
                "Outro",
            ],
        },
        {
            "id": "compra",
            "pergunta": "Como a venda fecha?",
            "multi": False,
            "opcoes": [
                "Pedido pelo WhatsApp",
                "Carrinho com pagamento no site",
                "Só mostrar o catálogo e o cliente chama",
                "Formulário de encomenda",
            ],
        },
        {
            "id": "entrega",
            "pergunta": "Como é a entrega e o pagamento? (pode marcar várias)",
            "multi": True,
            "opcoes": [
                "Entrega local",
                "Correios/transportadora",
                "Retirada no local",
                "Pix",
                "Cartão",
                "Dinheiro na entrega",
            ],
        },
        {
            "id": "estilo",
            "pergunta": "Qual estilo visual você prefere?",
            "multi": False,
            "opcoes": [
                "Moderno e limpo",
                "Elegante e sofisticado",
                "Colorido e jovem",
                "Rústico e artesanal",
            ],
        },
        {
            "id": "secoes",
            "pergunta": "Quais seções a loja deve ter? (pode marcar várias)",
            "multi": True,
            "opcoes": [
                "Início",
                "Catálogo de produtos",
                "Promoções",
                "Sobre a loja",
                "Depoimentos",
                "Formas de pagamento",
                "Contato",
            ],
        },
    ],
    "portfolio": [
        {
            "id": "area",
            "pergunta": "Qual é a sua área de trabalho?",
            "multi": False,
            "opcoes": [
                "Design/arte",
                "Fotografia",
                "Programação/tecnologia",
                "Redação/conteúdo",
                "Música/áudio",
                "Outro",
            ],
        },
        {
            "id": "trabalhos",
            "pergunta": "Como quer mostrar os trabalhos?",
            "multi": False,
            "opcoes": [
                "Uma página só com todos",
                "Uma página por projeto",
                "Galeria com fotos grandes",
                "Lista simples com links",
            ],
        },
        {
            "id": "objetivo",
            "pergunta": "O que você quer que aconteça? (pode marcar várias)",
            "multi": True,
            "opcoes": [
                "Ser contratado",
                "Mostrar currículo",
                "Vender um serviço",
                "Divulgar redes sociais",
                "Participar de projetos",
            ],
        },
        {
            "id": "estilo",
            "pergunta": "Qual estilo visual você prefere?",
            "multi": False,
            "opcoes": [
                "Minimalista e elegante",
                "Criativo e ousado",
                "Escuro e moderno",
                "Claro e leve",
            ],
        },
    ],
    "landing": [
        {
            "id": "oferta",
            "pergunta": "O que você está oferecendo nessa página?",
            "multi": False,
            "opcoes": [
                "Um produto",
                "Um serviço",
                "Um curso/mentoria",
                "Um evento",
                "Uma consultoria gratuita (captar contato)",
            ],
        },
        {
            "id": "acao",
            "pergunta": "Qual é a ação principal?",
            "multi": False,
            "opcoes": [
                "Chamar no WhatsApp",
                "Preencher formulário",
                "Comprar agora",
                "Agendar uma conversa",
                "Entrar no grupo/lista",
            ],
        },
        {
            "id": "prova",
            "pergunta": "O que serve de prova de confiança? (pode marcar várias)",
            "multi": True,
            "opcoes": [
                "Depoimentos de clientes",
                "Números/resultados",
                "Fotos antes e depois",
                "Selo/parceria",
                "Garantia",
                "Não tenho ainda",
            ],
        },
        {
            "id": "estilo",
            "pergunta": "Qual estilo visual você prefere?",
            "multi": False,
            "opcoes": [
                "Direto e objetivo",
                "Elegante e sofisticado",
                "Urgente e chamativo",
                "Limpo e confiável",
            ],
        },
    ],
    "blog": [
        {
            "id": "tema",
            "pergunta": "Sobre o que você escreve?",
            "multi": True,
            "opcoes": [
                "Tecnologia",
                "Receitas/comida",
                "Viagens",
                "Finanças",
                "Saúde/ bem-estar",
                "Humor",
                "Notícias",
                "Outro",
            ],
        },
        {
            "id": "organizacao",
            "pergunta": "Como organizar os posts?",
            "multi": False,
            "opcoes": [
                "Lista simples do mais novo",
                "Categorias e tags",
                "Por assunto em seções",
            ],
        },
        {
            "id": "interacao",
            "pergunta": "Vai ter interação com o leitor? (pode marcar várias)",
            "multi": True,
            "opcoes": [
                "Comentários",
                "Newsletter por e-mail",
                "Compartilhar nas redes",
                "Busca de posts",
                "Nenhuma",
            ],
        },
    ],
    "outro": [
        {
            "id": "ideia",
            "pergunta": "O que você quer construir?",
            "multi": False,
            "opcoes": [
                "Um site",
                "Um aplicativo",
                "Uma loja virtual",
                "Um portfólio",
                "Uma página de vendas",
                "Um blog",
            ],
        },
    ],
}

# A primeira etapa de qualquer projeto: o nome. Perguntar cedo evita site sem
# identidade (o erro mais comum — "Bem-vindo ao nosso site").
_ETAPA_NOME = {
    "id": "nome",
    "pergunta": "Qual é o nome do negócio ou projeto?",
    "multi": False,
    "livre": True,
    "opcoes": [],
}


def _sem_acento(texto: str) -> str:
    import unicodedata

    bruto = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in bruto if unicodedata.category(c) != "Mn")


def tipo_do_pedido(message: str) -> str:
    """Deduz o tipo de projeto pelo texto, para escolher as etapas."""
    texto = _sem_acento((message or "").lower())
    import re

    if re.search(r"\b(app|aplicativ\w*)", texto):
        return "app"
    if re.search(r"\b(loja|e-?commerce|marketplace|vender)", texto):
        return "loja"
    if re.search(r"\b(portfolio|portifolio)", texto):
        return "portfolio"
    if re.search(r"\b(landing|pagina de vendas|one-page)", texto):
        return "landing"
    if re.search(r"\b(blog)", texto):
        return "blog"
    return "site"


def etapas(message: str) -> list[dict]:
    """Etapas da entrevista para este pedido, com o nome sempre em primeiro."""
    tipo = tipo_do_pedido(message)
    lista = [dict(_ETAPA_NOME)] + [dict(e) for e in _ETAPAS.get(tipo, _ETAPAS["outro"])]
    return lista


def titulo_do_tipo(tipo: str) -> str:
    return {
        "site": "site",
        "app": "aplicativo",
        "loja": "loja virtual",
        "portfolio": "portfólio",
        "landing": "página de vendas",
        "blog": "blog",
    }.get(tipo, "projeto")


def intro(message: str) -> str:
    """Frase que acompanha a primeira etapa."""
    tipo = tipo_do_pedido(message)
    return (
        f"Boa! Vou montar seu {titulo_do_tipo(tipo)} — mas primeiro me responde "
        "estas rapidinho, escolhendo as opções. Assim já sai do jeito que você "
        "quer, sem retrabalho."
    )


# --------------------------------------------------------- memória da conversa
#
# A entrevista precisa VOLTAR quando o usuário recarrega a conversa (ou reabre
# o app). O evento do stream só existe ao vivo; ao ler do banco a mensagem é
# texto puro. Então o texto salvo leva um marcador invisível no fim com o tipo
# e o pedido original — na leitura, o backend reconstrói as etapas e o painel
# reaparece igual. O marcador é removido antes de mostrar ao usuário.

_MARCA = "\u2063"  # separador invisível (invisible separator), não aparece


def com_marca(texto: str, message: str) -> str:
    """Anexa ao texto o marcador que permite reconstruir a entrevista depois."""
    tipo = tipo_do_pedido(message)
    assunto = " ".join((message or "").split())[:300]
    return f"{texto}{_MARCA}{tipo}{_MARCA}{assunto}"


def do_texto_salvo(texto: str) -> tuple[str, dict | None]:
    """Separa o texto visível da entrevista gravada.

    Devolve ``(texto_limpo, dados_da_entrevista_ou_None)``. Quando não há
    marcador, devolve o texto intacto e ``None``.
    """
    if _MARCA not in (texto or ""):
        return texto, None
    partes = texto.split(_MARCA)
    if len(partes) < 3:
        return texto, None
    limpo = _MARCA.join(partes[:-2])
    tipo, assunto = partes[-2], partes[-1]
    return limpo, {
        "tipo": tipo,
        "assunto": assunto,
        "etapas": etapas(assunto),
    }
