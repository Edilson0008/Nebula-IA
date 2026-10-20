"""
Camada de persistência da Nébula — Supabase (Postgres).

Antes disto o banco era um SQLite no disco do servidor. No plano grátis do
Render o disco é apagado a cada reinício, então as conversas sumiam. Aqui os
dados ficam no Supabase: permanentes, de graça e sem reinício.

Como funciona a separação por pessoa:
    cada conversa/memória tem um `owner` (a "sala" da pessoa). O site manda o
    apelido escolhido e o backend só enxerga os dados daquele apelido.

As funções têm os MESMOS nomes do antigo `db.py`; o resto do servidor não
precisou mudar.
"""

from __future__ import annotations

import contextvars
import os
from datetime import datetime, timezone
from typing import Any

import httpx

# --------------------------------------------------------------------------
# Sala atual (a "conta" de quem está falando).
#
# Em vez de passar o apelido por todas as funções (são dezenas de chamadas),
# guardamos a sala do pedido numa variável de contexto: cada requisição tem a
# sua, sem misturar com as outras. O servidor define uma vez por pedido.
# --------------------------------------------------------------------------
_sala_atual: contextvars.ContextVar[str] = contextvars.ContextVar(
    "nebula_sala", default="local"
)


def definir_sala(sala: str) -> None:
    """Define a sala do pedido atual (chamado uma vez por requisição)."""
    _sala_atual.set(sala or "local")


def sala_atual() -> str:
    return _sala_atual.get()


def _own(owner: str | None) -> str:
    """Devolve a sala: a informada ou a do pedido atual."""
    return owner or _sala_atual.get() or "local"

# --------------------------------------------------------------------------
# Endereço e chave do projeto Supabase (vêm das variáveis de ambiente).
# --------------------------------------------------------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

# Quanto tempo esperar o Supabase responder antes de considerar falha.
_TIMEOUT = 20.0


def configurado() -> bool:
    """O Supabase está configurado neste servidor?"""
    return bool(SUPABASE_URL and SUPABASE_KEY)


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def _url(tabela: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{tabela}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pedir(
    metodo: str,
    tabela: str,
    *,
    params: dict[str, str] | None = None,
    corpo: Any = None,
    prefer: str | None = None,
) -> Any:
    """Faz uma chamada ao Supabase e devolve o JSON (ou None se vazio)."""
    if not configurado():
        raise RuntimeError(
            "SUPABASE_URL/SUPABASE_KEY não configurados. "
            "Defina as variáveis de ambiente para guardar as conversas."
        )

    extra = {"Prefer": prefer} if prefer else None
    with httpx.Client(timeout=_TIMEOUT) as cliente:
        r = cliente.request(
            metodo,
            _url(tabela),
            params=params,
            json=corpo,
            headers=_headers(extra),
        )
    if r.status_code >= 400:
        raise RuntimeError(f"Supabase {r.status_code}: {r.text[:400]}")
    if not r.content:
        return None
    try:
        return r.json()
    except ValueError:
        return None


def init_db() -> None:
    """Não há o que criar: as tabelas existem no Supabase.

    Mantida para o servidor poder chamar no boot sem mudar nada.
    """
    return None


# --------------------------------------------------------------------------
# Conversas
# --------------------------------------------------------------------------
def create_conversation(title: str, owner: str | None = None) -> int:
    owner = _own(owner)
    agora = _now()
    linhas = _pedir(
        "POST",
        "conversations",
        corpo=[{
            "owner": owner,
            "title": title,
            "created_at": agora,
            "updated_at": agora,
        }],
        prefer="return=representation",
    )
    if not linhas:
        raise RuntimeError("Não consegui criar a conversa no Supabase.")
    return int(linhas[0]["id"])


def list_conversations(owner: str | None = None) -> list[dict]:
    owner = _own(owner)
    linhas = _pedir(
        "GET",
        "conversations",
        params={
            "owner": f"eq.{owner}",
            "select": "id,title,project,created_at,updated_at",
            "order": "updated_at.desc",
        },
    )
    return linhas or []


def get_conversation(conversation_id: int, owner: str | None = None) -> dict | None:
    owner = _own(owner)
    linhas = _pedir(
        "GET",
        "conversations",
        params={
            "id": f"eq.{conversation_id}",
            "owner": f"eq.{owner}",
            "select": "id,title,project,created_at,updated_at",
            "limit": "1",
        },
    )
    return linhas[0] if linhas else None


def conversation_exists(conversation_id: int, owner: str | None = None) -> bool:
    return get_conversation(conversation_id, _own(owner)) is not None


def set_project(conversation_id: int, project: str, owner: str | None = None) -> None:
    owner = _own(owner)
    _pedir(
        "PATCH",
        "conversations",
        params={"id": f"eq.{conversation_id}", "owner": f"eq.{owner}"},
        corpo={"project": project},
    )


def delete_conversation(conversation_id: int, owner: str | None = None) -> bool:
    owner = _own(owner)
    if not conversation_exists(conversation_id, owner):
        return False
    _pedir(
        "DELETE",
        "conversations",
        params={"id": f"eq.{conversation_id}", "owner": f"eq.{owner}"},
    )
    return True


def rename_conversation(conversation_id: int, title: str, owner: str | None = None) -> bool:
    owner = _own(owner)
    if not conversation_exists(conversation_id, owner):
        return False
    _pedir(
        "PATCH",
        "conversations",
        params={"id": f"eq.{conversation_id}", "owner": f"eq.{owner}"},
        corpo={"title": title, "updated_at": _now()},
    )
    return True


def _touch(conversation_id: int) -> None:
    """Atualiza a data da conversa (para ela subir na lista)."""
    _pedir(
        "PATCH",
        "conversations",
        params={"id": f"eq.{conversation_id}"},
        corpo={"updated_at": _now()},
    )


# --------------------------------------------------------------------------
# Mensagens
# --------------------------------------------------------------------------
def _load_attachments(raw) -> list[dict]:
    if not raw:
        return []
    import json

    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return []


def get_messages(conversation_id: int) -> list[dict]:
    linhas = _pedir(
        "GET",
        "messages",
        params={
            "conversation_id": f"eq.{conversation_id}",
            "select": "id,conversation_id,role,content,attachments,created_at",
            "order": "id.asc",
        },
    )
    resultado = []
    for linha in linhas or []:
        linha["attachments"] = _load_attachments(linha.get("attachments"))
        resultado.append(linha)
    return resultado


def get_message(message_id: int) -> dict | None:
    linhas = _pedir(
        "GET",
        "messages",
        params={
            "id": f"eq.{message_id}",
            "select": "id,conversation_id,role,content,attachments,created_at",
            "limit": "1",
        },
    )
    if not linhas:
        return None
    linha = linhas[0]
    linha["attachments"] = _load_attachments(linha.get("attachments"))
    return linha


def add_message(
    conversation_id: int,
    role: str,
    content: str,
    attachments: list[dict] | None = None,
) -> int:
    import json

    payload = json.dumps(attachments, ensure_ascii=False) if attachments else None
    linhas = _pedir(
        "POST",
        "messages",
        corpo=[{
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "attachments": payload,
            "created_at": _now(),
        }],
        prefer="return=representation",
    )
    _touch(conversation_id)
    if not linhas:
        raise RuntimeError("Não consegui salvar a mensagem no Supabase.")
    return int(linhas[0]["id"])


def update_message(message_id: int, content: str) -> bool:
    linhas = _pedir(
        "PATCH",
        "messages",
        params={"id": f"eq.{message_id}"},
        corpo={"content": content},
        prefer="return=representation",
    )
    return bool(linhas)


def delete_messages_after(conversation_id: int, message_id: int) -> int:
    linhas = _pedir(
        "DELETE",
        "messages",
        params={
            "conversation_id": f"eq.{conversation_id}",
            "id": f"gt.{message_id}",
        },
        prefer="return=representation",
    )
    return len(linhas) if linhas else 0


# --------------------------------------------------------------------------
# Memórias (o que a Nébula aprende sobre a pessoa)
# --------------------------------------------------------------------------
def add_memory(
    conversation_id: int | None, content: str, embedding: bytes, owner: str | None = None
) -> int:
    owner = _own(owner)
    import base64

    linhas = _pedir(
        "POST",
        "memories",
        corpo=[{
            "owner": owner,
            "conversation_id": conversation_id,
            "content": content,
            "embedding": base64.b64encode(embedding).decode("ascii"),
            "created_at": _now(),
        }],
        prefer="return=representation",
    )
    if not linhas:
        raise RuntimeError("Não consegui salvar a memória no Supabase.")
    return int(linhas[0]["id"])


def _memoria_com_bytes(linha: dict) -> dict:
    import base64

    bruto = linha.get("embedding")
    if isinstance(bruto, str) and bruto:
        try:
            linha["embedding"] = base64.b64decode(bruto)
        except (ValueError, TypeError):
            linha["embedding"] = b""
    else:
        linha["embedding"] = b""
    return linha


def all_memories(owner: str | None = None) -> list[dict]:
    owner = _own(owner)
    linhas = _pedir(
        "GET",
        "memories",
        params={
            "owner": f"eq.{owner}",
            "select": "id,conversation_id,content,embedding,created_at",
            "order": "id.asc",
        },
    )
    return [_memoria_com_bytes(l) for l in (linhas or [])]


def list_memories(owner: str | None = None) -> list[dict]:
    owner = _own(owner)
    linhas = _pedir(
        "GET",
        "memories",
        params={
            "owner": f"eq.{owner}",
            "select": "id,conversation_id,content,created_at",
            "order": "id.desc",
        },
    )
    return linhas or []


def delete_memory(memory_id: int, owner: str | None = None) -> bool:
    owner = _own(owner)
    linhas = _pedir(
        "DELETE",
        "memories",
        params={"id": f"eq.{memory_id}", "owner": f"eq.{owner}"},
        prefer="return=representation",
    )
    return bool(linhas)


# --------------------------------------------------------------------------
# Cofre: exportar/importar tudo o que é de uma pessoa
# --------------------------------------------------------------------------
def exportar_owner(owner: str | None = None) -> dict:
    owner = _own(owner)
    """Tudo o que é daquela pessoa, em JSON pronto para virar cópia."""
    convs = list_conversations(owner)
    dados_convs = []
    for c in convs:
        dados_convs.append({
            "id": c["id"],
            "title": c["title"],
            "project": c.get("project"),
            "created_at": c["created_at"],
            "updated_at": c["updated_at"],
            "messages": get_messages(int(c["id"])),
        })
    return {
        "versao": 2,
        "owner": owner,
        "gerado_em": _now(),
        "conversations": dados_convs,
        "memories": list_memories(owner),
    }


def importar_owner(pacote: dict, owner: str | None = None) -> dict:
    owner = _own(owner)
    """Devolve uma cópia inteira para a sala da pessoa.

    Limpa o que já existe antes, para não duplicar. Cada conversa mantém a
    ordem das mensagens.
    """
    if not isinstance(pacote, dict):
        raise ValueError("Cópia inválida.")
    convs = pacote.get("conversations") or []
    memories = pacote.get("memories") or []
    if not isinstance(convs, list) or not isinstance(memories, list):
        raise ValueError("Cópia inválida.")

    # Limpa a sala (as mensagens somem junto, por cascata).
    _pedir("DELETE", "conversations", params={"owner": f"eq.{owner}"})
    _pedir("DELETE", "memories", params={"owner": f"eq.{owner}"})

    conversas = 0
    mensagens = 0
    for c in convs:
        if not isinstance(c, dict) or not c.get("title"):
            continue
        novo_id = create_conversation(str(c["title"]), owner)
        if c.get("project"):
            set_project(novo_id, str(c["project"]), owner)
        for m in c.get("messages") or []:
            if not isinstance(m, dict) or not m.get("content"):
                continue
            anexos = m.get("attachments") if isinstance(m.get("attachments"), list) else None
            add_message(novo_id, m.get("role", "user"), str(m["content"]), anexos)
            mensagens += 1
        conversas += 1

    for m in memories:
        if not isinstance(m, dict) or not m.get("content"):
            continue
        bruto = m.get("embedding") or b""
        emb = bruto if isinstance(bruto, bytes) else str(bruto).encode("utf-8")
        add_memory(None, str(m["content"]), emb, owner)

    return {
        "conversas": conversas,
        "mensagens": mensagens,
        "memorias": len(memories),
    }


def banco_vazio(owner: str | None = None) -> bool:
    owner = _own(owner)
    try:
        return not list_conversations(owner) and not list_memories(owner)
    except Exception:
        return True


def estatisticas(owner: str | None = None) -> dict:
    owner = _own(owner)
    convs = list_conversations(owner)
    total_msg = 0
    for c in convs:
        total_msg += len(get_messages(int(c["id"])))
    return {
        "conversas": len(convs),
        "mensagens": total_msg,
        "memorias": len(list_memories(owner)),
    }
