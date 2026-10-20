# Nébula

IA geral própria com a API do Gemini. Backend em **Python (FastAPI)** + frontend **React (Vite + Tailwind)** inspirado na interface do Gemini.

## Estrutura

```
minha-ia/
├── backend/          # FastAPI + Gemini + SQLite
│   ├── main.py             # rotas da API
│   ├── gemini_client.py    # única ponte com a API do Gemini
│   ├── agent.py            # modo agente: ferramentas de arquivo e terminal
│   ├── design_guide.py     # manual de agência + biblioteca de guias (sob demanda)
│   ├── guias/              # 300+ agentes especialistas (design, marketing, engenharia…)
│   ├── db.py               # conversas, mensagens e memórias (SQLite)
│   ├── memory.py           # memória de longo prazo (embeddings)
│   ├── workspace.py        # criação dos arquivos/sites que a IA gera
│   └── .env.example        # modelo de configuração
└── frontend/         # chat web (React + Vite + Tailwind)
```

## O que a Nébula faz hoje

- Conversa em **streaming** (a resposta aparece sendo escrita) com **markdown** e realce de código.
- **Histórico** de conversas salvo em SQLite (criar, abrir, renomear, buscar e apagar).
- **Memória de longo prazo**: ela aprende fatos sobre você (nome, gostos, projetos) e lembra
  em conversas futuras. Dá para ver, apagar e desligar no botão **Memória** da barra lateral.
- **Cria arquivos de verdade**: peça um site e ela salva `index.html`, `style.css` etc.
  Cada arquivo aparece na conversa como um cartão com **Pré-visualizar**, **Abrir**,
  **Baixar** e **Copiar** — sem precisar copiar e colar código.
- **Sites nível agência**: o pedido de site carrega um **manual de design** (tokens,
  componentes com todos os estados, responsivo, acessibilidade, copy/conversão,
  fotos reais e SEO) destilado de uma biblioteca de **300+ agentes especialistas**
  que ela também pode consultar sob demanda com a ferramenta `guia`.
- **Modo offline**: o botão de globo no topo faz o site sair **100% sem internet**
  (sem CDN, fontes do sistema, ícones em SVG) — ele abre em qualquer lugar, até sem sinal.
- **Anexos**: envie imagens, PDF ou texto junto com a mensagem (com pré-visualização).
- **Ditado por voz** (pt-BR), **parar geração**, **regenerar** e **editar** mensagens.
- **Pode ser instalada como app (PWA)** direto pelo navegador do celular.
- **Não fica sem resposta**: são vários modelos do Gemini. Se a cota (por modelo) do
  plano gratuito acabar, ela **troca sozinha** para o próximo da lista e você continua
  conversando. O nome do modelo que respondeu aparece no topo da tela.
- **Modo agente (mãos e pernas)**: pedidos de compilar/instalar/executar fazem a Nébula
  **usar ferramentas de verdade** — ler e escrever arquivos e rodar comandos no terminal —
  até a tarefa ficar pronta. Comandos **dentro da pasta do projeto** rodam direto; os de
  **fora** aparecem como um cartão **Permitir/Negar** na conversa. Veja "Modo agente" abaixo.
- **Compila apps Android nativos (.apk)**: com o kit Android instalado (ver abaixo), ela
  monta o projeto (Gradle/AGP), roda `gradle assembleDebug` sozinha, conserta erros de
  build e te entrega o `.apk` no cartão de arquivo — pronto para instalar no celular.

## Onde colocar a sua chave

O projeto existe em **dois lugares**, e o backend lê os dois:

| Local | Para que serve | Como acessar |
|---|---|---|
| `/sdcard/Download/minha-ia` | cópia editável | gerenciador de arquivos do celular |
| `/root/minha-ia` | onde o servidor roda (tem `venv/` e `node_modules/`) | terminal do sistema |

**A cópia do celular tem prioridade.** Então o caminho mais fácil é:

1. Abra `/sdcard/Download/minha-ia/backend/.env` no editor de texto
2. Substitua `sua_chave_aqui` pela sua chave do AI Studio
3. Salve pronto — o backend já passa a usar essa chave

Valores de exemplo (`sua_chave_aqui`) são ignorados, então o servidor nunca quebra por esquecimento.

## Onde os arquivos criados são salvos

Tudo o que a IA cria vai para **`WORKSPACE_DIR`** (padrão no celular:
`/sdcard/Download/nebula-projetos`). Cada conversa vira uma pasta:

```
/sdcard/Download/nebula-projetos/meu-site-12/
├── index.html
└── style.css
```

Você pode abrir pelo cartão na conversa **ou** direto no gerenciador de arquivos.
Os arquivos também ficam disponíveis em `http://localhost:8000/files/<projeto>/<arquivo>`.

## Como rodar

### 1. Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # cole sua chave em GEMINI_API_KEY
uvicorn main:app --reload --port 8000
```

Chave da API: https://aistudio.google.com/apikey (gratuita com limite de uso)

### 2. Frontend (em outro terminal)

```bash
cd frontend
npm install
npm run dev
```

Abra http://localhost:5173 — o Vite repassa `/api` e `/files` para o backend em `:8000`.

## Limite do plano gratuito (importante)

No plano gratuito a cota é **por modelo** e por dia — hoje são **20 mensagens/dia**
para o `gemini-3.8-flash`.

A Nébula se defende disso de três formas:

1. **Modelos de reserva** — quando a cota de um acaba, ela **troca sozinha** para o
   próximo da lista. Cada reserva é como "mais mensagens", e o nome do modelo que
   respondeu aparece no topo da tela.
2. **Retentativa com espera** — quando o erro é passageiro (o Google pediu para
   esperar, servidor sobrecarregado, oscilação de rede), ela **tenta de novo
   sozinha**, esperando um pouco mais a cada tentativa, em vez de mostrar erro.
   É isso que evita a maioria das "quedas".
3. **Modelo próprio para a memória** — `GEMINI_MEMORY_MODEL` usa uma cota separada,
   então aprender fatos **não gasta** as suas conversas.
4. **Escolha do modelo mais rápido** — ela guarda qual modelo respondeu bem (e em
   quanto tempo) e **começa por ele** na próxima mensagem. Modelo que demora mais
   de 7 s para começar a responder é trocado na hora; cota diária esgotada fica
   de fora até a virada do dia, em vez de ser reprovada a cada mensagem. Esse
   aprendizado sobrevive a reinícios (`/var/lib/nebula/gemini-state.json` ou,
   sem permissão nessa pasta, um arquivo ao lado do backend).

Antes disso, cada mensagem percorria a lista inteira de reservas: um modelo
sobrecarregado segurava a resposta por 20 s ou mais. Agora a primeira resposta
costuma sair em **1 a 4 segundos** quando a cota está saudável.

Se ainda assim nada tiver cota, aparece um aviso **âmbar** (não é falha, é só o
limite do dia) com um botão **Tentar de novo**. O que resolve de vez é ativar o
faturamento no AI Studio.

Dica: os modelos da família `2.5` aparecem na lista da API mas respondem erro 404
para contas novas — por isso não estão nas reservas.

## Configuração (backend/.env)

| Variável | Padrão | Para que serve |
|---|---|---|
| `GEMINI_API_KEY` | — | sua chave do AI Studio |
| `GEMINI_MODEL` | `gemini-3.8-flash` | modelo principal das conversas |
| `GEMINI_FALLBACK_MODELS` | `gemini-3.7-flash,gemini-3.6-flash,…` | reservas usadas quando a cota acaba |
| `GEMINI_MEMORY_MODEL` | `gemini-3.1-flash-lite` | modelo leve que aprende os fatos |
| `GEMINI_MEMORY_FALLBACK_MODELS` | `gemini-3.5-flash-lite` | reservas da memória |
| `GEMINI_EMBEDDING_MODEL` | `gemini-embedding-001` | vetores da memória |
| `WORKSPACE_DIR` | `backend/workspace` | pasta onde os arquivos criados são salvos |
| `MEMORY_MIN_SCORE` | `0.66` | quão parecido um fato precisa ser para ser lembrado |
| `AGENT_ENABLED` | `1` | liga/desliga o modo agente (ferramentas + terminal) |
| `AGENT_SHELL` | `ask` | trava dos comandos: `ask` (fora do projeto pede aprovação), `always`, `never` |
| `AGENT_APPROVAL_TIMEOUT` | `120` | segundos esperando o clique em Permitir/Negar antes de negar |

## Modo agente (mãos e pernas)

Quando a mensagem pede algo **prático** — "compile um app", "instale as dependências",
"rode os testes", "execute esse comando" — ou depende do **agora** — "últimas
notícias", "como está o clima", "quanto está o dólar", "quem ganhou o jogo" — a
Nébula entra no modo agente: em vez de só mostrar código, ela **executa a tarefa**
(ou consulta a fonte certa) num laço de ferramentas:

| Ferramenta | O que faz |
|---|---|
| `listar` / `ler` / `escrever` / `criar_pasta` / `apagar` | enxerga e mexe nos arquivos do projeto |
| `executar` | roda comandos (shell) com a pasta do projeto como diretório atual |
| `servidor` | sobe um **servidor de teste** em segundo plano (localhost) pra você ver no navegador enquanto ajustam — `iniciar` devolve a URL clicável, `status` confirma, `parar` derruba |
| `clima` | tempo agora + previsão de qualquer cidade (Open-Meteo) |
| `hora` | data/hora atuais de qualquer fuso (Brasil ou exterior) |
| `noticias` | manchetes do dia ou de um assunto (Google Notícias pt-BR) |
| `buscar` | busca na web em tempo real (DuckDuckGo + Bing + notícias) |
| `imagens` | fotos reais e livres de um tema (Openverse + Wikimedia Commons), prontas pra `<img>` |
| `guia` | consulta a **biblioteca de 300+ agentes especialistas** (`buscar`/`ler`/`listar`) antes de criar site/app |

As ferramentas de **tempo real** (clima, hora, notícias, busca, imagens) são gratuitas e
não precisam de chave de API — a Nébula usa elas antes de responder qualquer
coisa que dependa do que está acontecendo agora (ela não "sabe" nada depois do
seu treinamento).

**Manual de agência (sites nível profissional):** em todo pedido de
site/página/app entra, junto das regras de front-end, um **manual de agência**
destilado de uma biblioteca de 300+ agentes especialistas (UI Designer, UX
Architect, Brand Guardian, UI Finish-Gate Reviewer, Visual Storyteller,
Whimsy Injector, Persona Walkthrough, SEO e Frontend Developer). Ele cobre:
contrato de design (usuário/tarefa/ação primária), design tokens (cor,
tipografia com `clamp()`, espaçamento, sombras), biblioteca de componentes com
**todos os estados** (hover/focus-visible/disabled/loading/erro/vazio),
responsivo 360→1440px, acessibilidade WCAG AA, copy e conversão (LIFT, Cialdini,
Fogg), uso de fotos reais, SEO/`JSON-LD` e um **finish gate** que reprova o
"site genérico que serviria para qualquer empresa".

A biblioteca completa fica em `backend/guias/` (323 arquivos) e é consultável
por demanda com a ferramenta `guia`: `buscar` acha os agentes de um assunto
(com sinônimos pt→en), `ler` abre um agente inteiro e `listar` mostra as áreas.
Assim nada de conhecimento se perde e o prompt do dia a dia continua curto.

**Fotos reais no site (sem placeholder):** antes de gerar um site, o sistema
busca fotos do tema **primeiro no Openverse** (o buscador oficial de mídia
Creative Commons — busca por *conteúdo*, cobrindo Flickr CC, Wikimedia,
Unsplash, NASA…) e **depois no Wikimedia Commons** como reserva. Nenhum dos
dois exige chave. As URLs entram no prompt e as regras de design exigem usar só
essas, com `alt` em português e `loading="lazy"`. O tema sai da frase ("site
para uma academia" → "academia musculação"), a lista de arquivos entre
parênteses ("(index.html + style.css)") e o **nome de marca inventado**
("chamada Forja Fitness") ficam de fora. No modo offline não entra foto remota
nenhuma — só SVG/CSS.

**Por que o Openverse (e não o Commons sozinho):** o Commons é uma enciclopédia
com *nome de arquivo* — buscar "animal" ali devolvia "Bañeira animais"
(fresco de igreja). O Openverse busca por relevância de conteúdo: `lua` acha a
Lua, `leão` acha o animal, `tamanduá-bandeira` acha o bicho. A primeira consulta
de cada termo demora ~9 s do lado deles (cache frio); por isso o sistema
**pré-aquece em paralelo** os assuntos citados no pedido assim que ele chega, e
a ferramenta `imagens` responde na hora.

**Como a busca escolhe a foto (e evita a foto errada):** nada entra sem passar
por crivo:

- **Casamento por palavra inteira** (com plural/feminino): antes, `floricultura`
  virava `flore` e casava com "Pavillon de **Flore**" e "Angel **Flores**"
  (pessoa); `pão` casava com o morro **Pão de Açúcar**. Agora casa a palavra.
- **Nota por posição**: o tema no começo do título é foto do tema ("Taki
  **Pizzaria**"); enterrado no fim é paisagem ("Headquarters of Greenlandic
  newspaper … next to the **pizzaria**"). Título com o tema adiante perde lugar.
- **Consulta certa para cada tipo de palavra**: três listas.
  - **Homônimos** (`_EM_INGLES`): o português é ambíguo no acervo, então busca
    em **inglês** — `leão` acha "Carneiro Leão" (sobrenome) e "Fábrica Leão"
    (empresa), mas `lion` acha o animal; `manga` acha roupa, `mango` acha a
    fruta; `banco` acha banco de praça, `bench` separa; `marte` acha "Marte
    Röling" (nome) e "Mercado Mart", mas `mars planet` acha o planeta.
  - **Ambíguas** (`_DESAMBIGUA`): a expansão é obrigatória e vem primeiro
    ("academia" acha academia de letras e My Hero Academia; "musculação" acha
    a academia de ginástica; "pizzaria" acha a fachada, "pizza" acha o prato).
  - **Normais** (`_SINONIMOS`): o termo pedido vem primeiro e o sinônimo só
    completa o que faltar ("flores" acha sobrenome de gente).
- **Fora:** logotipo, brasão, mapa, carta, pôster, série de TV, **exposição/
  feira/museu** (quando a busca é uma categoria, vira estande de museu),
  **produto com o mesmo nome** (unha "Galáxia", camisa de time, "Ford Galáxia")
  e conteúdo adulto. Foto que não bate: **foto errada é pior que foto nenhuma**
  — aí o item sai em SVG.
- **Categoria não é assunto**: pedir foto de "animais raros", "bem
  profissional" ou "didático" não devolve nada — não existe foto de "animal
  genérico" nem de "profissional"; o certo é buscar o bicho/o assunto concreto.
- **Sem repetição**: o prompt proíbe repetir a mesma foto; faltou foto para um
  item, ele fica em SVG em vez de mostrar a mesma imagem de novo.

**Diretriz de mídia (no system prompt, em todo site):** o manual de design exige
que **nenhuma URL de imagem seja inventada**, que **cada imagem corresponda
estritamente ao assunto do bloco** (card de leão → foto de leão; card de
tecnologia → foto de computador/código) e que toda `<img>` tenha **`alt`
descritivo em português**, classes `object-cover` + raio, e ícones sempre em
SVG/Lucide (nunca `<img>` para ícone). Proíbe explicitamente os serviços de
imagem dinâmica por termo (`picsum`, `source.unsplash`, `placehold.co`,
`loremflickr`) — eles quebram e deixam a página com imagem vazia; URL de imagem
só sai da lista real. O prompt também exige Tailwind via CDN e fonte **Inter**
(com par display+corpo quando o projeto pedir personalidade).

**Blocos com assuntos diferentes (um card por animal/produto):** a busca de um
tema só não cobre vários assuntos. Nesse caso o prompt manda a IA chamar a
ferramenta `imagens` **uma vez por assunto** (`tema="leão"`, `tema="elefante"`…)
antes de escrever o código e usar a foto certa em cada bloco. Exemplo real
(página de zoológico com leão, elefante, tigre e golfinho): 4 chamadas, 4 fotos
distintas — `Lion male`, `Elefante africano de savana`, `Tiger-2`,
`A bottlenose dolphin at Cromarty` — cada uma no seu card, com alt em pt-BR.

**Ajuste depois de pronto ("adicione ilustrações dos produtos"):** pedidos de
mudança numa página já criada ("troque as fotos do cardápio", "coloque imagens
nos produtos") também entram no modo build e **buscam fotos de novo**. O tema
vem do **pedido original da conversa** ("crie um site para uma pizzaria…"), não
do ajuste curto — mesmo que o ajuste contenha a palavra "cardápio", é o site
original que diz de que assunto é. E, quando a lista chega vazia, o prompt manda
a IA **chamar a ferramenta `imagens`** em vez de dizer que "não consegue buscar
imagens" ou empurrar o usuário para Unsplash/Pexels.

**Fluxo de teste antes de compilar:** pedindo um site/app, a Nébula sobe o
servidor de teste e passa a URL; você abre no navegador, manda ajustar quantas
quiser (sem compilar nada) e só quando estiver pronto manda o build final —
pro app Android vale a mesma lógica: ajusta à vontade, compila no fim (os
builds seguintes são incrementais e rápidos). **APK só sob pedido**: quando o
build roda, o sistema mesmo copia o `.apk` final pra
`/sdcard/Download/<projeto>.apk` (é só instalar por lá; um rebuild sobrescreve
o arquivo, então nunca acumula APK velho).

O andamento aparece na conversa: o painel **Ferramentas** mostra cada passo (⏳/✅/❌)
e o rótulo do estágio ("Executando comando", "Escrevendo"…).

**Segurança (trava de comandos, `AGENT_SHELL`):**

- `ask` (padrão): comandos **dentro do projeto** rodam na hora; qualquer coisa **fora**
  (instalar pacote do sistema, escrever fora da área de trabalho, baixar arquivo) abre o
  cartão **Permitir/Negar** e o comando só roda depois do seu clique. Sem resposta em
  `AGENT_APPROVAL_TIMEOUT` segundos, nega sozinho.
- `never`: nunca roda nada fora do projeto.
- `always`: sem perguntas (use só se confiar no que a IA vai rodar).

Sempre **bloqueado**, nem com `always`: `.env` e `chat.db`, chaves SSH, formatar/apagar
discos, `sudo`/`root`, escrita fora do celular (`/etc`, `/system`…). O backend roda
**sem privilégios de root**, então na prática nada disso aconteceria mesmo sem a trava.

**Compilar Android:** o kit fica em `/opt/android-sdk` (JDK 21 + Gradle 8.11.1 +
SDK/build-tools). Como os binários do SDK são x86_64 e o aparelho é ARM64, existe
um diretório de **wrappers** (`/opt/android-sdk/wrappers`) que passa tudo pelo
emulador `qemu-x86_64` — a Nébula já recebe o `PATH` e o
`android.aapt2FromMavenOverride` prontos nas instruções do sistema. O `.apk` gerado é
detectado sozinho e vira cartão com **Baixar**.

## Roadmap (evolução)

- [x] Fase 1 — chat básico com histórico persistente
- [x] Fase 2 — respostas em streaming + markdown formatado
- [x] Fase 3 — memória de longo prazo (RAG com embeddings) + criação de arquivos
- [x] Fase 4 — anexos, ditado por voz, edição/regeneração de mensagens e PWA
- [x] Fase 5 — **modo agente**: ler/escrever arquivos + executar comandos com
      aprovação do usuário, e compilação de apps Android (.apk) no próprio aparelho
- [ ] Fase 6 — instalação do APK pelo celular (via `adb`/`Intent`) e build em background com fila

## API

| Rota | Método | Para que serve |
|---|---|---|
| `/api/chat` | POST | resposta completa de uma vez (`provider`: `auto`/`gemini`) |
| `/api/chat/stream` | POST | mesma coisa, mas em pedaços (streaming) |
| `/api/conversations` | GET | lista as conversas |
| `/api/conversations` | POST | cria uma conversa |
| `/api/conversations/{id}` | GET | mensagens de uma conversa |
| `/api/conversations/{id}` | PATCH | renomeia a conversa |
| `/api/conversations/{id}` | DELETE | apaga a conversa |
| `/api/memories` | GET | lista os fatos lembrados |
| `/api/memories/{id}` | DELETE | esquece um fato |
| `/api/approvals` | POST | responde um cartão de comando (`{id, approved}`) e destrava o agente |
| `/files/{projeto}/{arquivo}` | GET | entrega um arquivo criado pela IA |

O **streaming** usa Server-Sent Events com os eventos `meta` (id da conversa),
`status` (andamento, com `label` opcional do estágio), `delta` (pedaço de texto),
`tool` (passo das ferramentas: `phase` start/progress/end, `seq`, `name`, `ok`…),
`approval` (comando fora do projeto esperando aprovação: `id`, `command`, `reason`),
`files` (arquivos criados), `error` e `done` (informa qual modelo respondeu).

### Formato dos arquivos na resposta

Para criar arquivos, a IA escreve blocos marcados no texto:

```
```file:index.html
<!doctype html>
...
```
```

O backend extrai esses blocos, grava cada arquivo na pasta do projeto e manda
um evento `files` com nome, url e nº de linhas. O frontend troca o bloco por um
cartão de arquivo.
