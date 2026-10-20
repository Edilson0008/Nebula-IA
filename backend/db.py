"""Camada de persistência: conversas, mensagens e memórias (SQLite)."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "chat.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('user', 'model')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER,
                content TEXT NOT NULL,
                embedding BLOB NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        _ensure_column(conn, "conversations", "project", "project TEXT")
        # Anexos da mensagem (imagens/arquivos) guardados como JSON.
        _ensure_column(conn, "messages", "attachments", "attachments TEXT")


def _ensure_column(
    conn: sqlite3.Connection, table: str, column: str, ddl: str
) -> None:
    """Adiciona uma coluna em bancos que já existiam (migração simples)."""
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


# ----------------------------------------------------------------- conversas


def create_conversation(title: str) -> int:
    now = _now()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO conversations (title, created_at, updated_at) VALUES (?, ?, ?)",
            (title, now, now),
        )
        return int(cur.lastrowid)


def list_conversations() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, title, updated_at FROM conversations ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]


def get_conversation(conversation_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, title, project FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        return dict(row) if row else None


def conversation_exists(conversation_id: int) -> bool:
    return get_conversation(conversation_id) is not None


def set_project(conversation_id: int, project: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE conversations SET project = ? WHERE id = ?",
            (project, conversation_id),
        )


def delete_conversation(conversation_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        return cur.rowcount > 0


def rename_conversation(conversation_id: int, title: str) -> bool:
    """Troca o título da conversa (como o "renomear" do app do Gemini)."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE conversations SET title = ? WHERE id = ?",
            (title, conversation_id),
        )
        return cur.rowcount > 0


# ------------------------------------------------------------------ mensagens


def _load_attachments(raw) -> list[dict]:
    """Converte a coluna JSON dos anexos numa lista (nunca quebra)."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return data if isinstance(data, list) else []


def get_messages(conversation_id: int) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, role, content, attachments, created_at FROM messages "
            "WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        ).fetchall()
    messages = []
    for row in rows:
        item = dict(row)
        item["attachments"] = _load_attachments(item.get("attachments"))
        messages.append(item)
    return messages


def get_message(message_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, conversation_id, role, content, attachments FROM messages "
            "WHERE id = ?",
            (message_id,),
        ).fetchone()
    if row is None:
        return None
    item = dict(row)
    item["attachments"] = _load_attachments(item.get("attachments"))
    return item


def add_message(
    conversation_id: int,
    role: str,
    content: str,
    attachments: list[dict] | None = None,
) -> int:
    now = _now()
    payload = json.dumps(attachments, ensure_ascii=False) if attachments else None
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO messages (conversation_id, role, content, attachments, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (conversation_id, role, content, payload, now),
        )
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conversation_id),
        )
        return int(cur.lastrowid)


def update_message(
    message_id: int, content: str, attachments: list[dict] | None = None
) -> bool:
    """Reescreve uma mensagem (usado ao editar e gerar de novo)."""
    payload = json.dumps(attachments, ensure_ascii=False) if attachments else None
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE messages SET content = ?, attachments = ? WHERE id = ?",
            (content, payload, message_id),
        )
        return cur.rowcount > 0


def delete_messages_after(conversation_id: int, message_id: int) -> int:
    """Apaga tudo que veio depois de uma mensagem (regenerar/editar)."""
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM messages WHERE conversation_id = ? AND id > ?",
            (conversation_id, message_id),
        )
        return cur.rowcount


# ------------------------------------------------------------------ memórias


def add_memory(conversation_id: int | None, content: str, embedding: bytes) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO memories (conversation_id, content, embedding, created_at) "
            "VALUES (?, ?, ?, ?)",
            (conversation_id, content, embedding, _now()),
        )
        return int(cur.lastrowid)


def all_memories() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, content, embedding, created_at FROM memories ORDER BY id DESC"
        ).fetchall()
        return [dict(row) for row in rows]


def list_memories() -> list[dict]:
    """Como all_memories, mas sem os vetores (para enviar ao frontend)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, content, created_at FROM memories ORDER BY id DESC"
        ).fetchall()
        return [dict(row) for row in rows]


def delete_memory(memory_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        return cur.rowcount > 0
