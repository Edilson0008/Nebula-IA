"""
Migração: leva as conversas do banco SQLite antigo para o Supabase.

Uso:
    SUPABASE_URL=... SUPABASE_KEY=... python3 migrar_sqlite_para_supabase.py \
        /caminho/chat.db <apelido>

O que faz:
    - lê todas as conversas, mensagens e memórias do SQLite antigo;
    - grava tudo na sala <apelido> do Supabase, na mesma ordem;
    - mostra um resumo no fim.

Rode UMA vez, depois de rodar o schema.sql no Supabase.
"""

import base64
import sqlite3
import sys

import db_supabase as db


def migrar(caminho_sqlite: str, apelido: str) -> None:
    db.definir_sala(apelido)

    origem = sqlite3.connect(caminho_sqlite)
    origem.row_factory = sqlite3.Row

    conversas = origem.execute(
        "SELECT id, title, project, created_at FROM conversations ORDER BY id"
    ).fetchall()
    print(f"SQLite: {len(conversas)} conversa(s) para levar para a sala '{apelido}'.")

    # Limpa a sala antes, para não duplicar se rodar de novo.
    print("Limpando a sala no Supabase…")
    db.importar_owner({"conversations": [], "memories": []}, apelido)

    total_msg = 0
    for c in conversas:
        novo_id = db.create_conversation(c["title"], apelido)
        if c["project"]:
            db.set_project(novo_id, c["project"], apelido)
        mensagens = origem.execute(
            "SELECT role, content, attachments, created_at FROM messages "
            "WHERE conversation_id = ? ORDER BY id",
            (c["id"],),
        ).fetchall()
        for m in mensagens:
            anexos = None
            if m["attachments"]:
                import json

                try:
                    anexos = json.loads(m["attachments"])
                except ValueError:
                    anexos = None
            db.add_message(novo_id, m["role"], m["content"], anexos)
            total_msg += 1
        print(f"  [{c['id']} -> {novo_id}] {c['title'][:45]} ({len(mensagens)} msg)")

    memorias = origem.execute(
        "SELECT content, embedding FROM memories ORDER BY id"
    ).fetchall()
    for m in memorias:
        bruto = m["embedding"] or b""
        emb = bruto if isinstance(bruto, bytes) else base64.b64decode(bruto)
        db.add_memory(None, m["content"], emb, apelido)

    origem.close()

    print()
    print("Pronto!")
    print(f"  conversas: {len(conversas)}")
    print(f"  mensagens: {total_msg}")
    print(f"  memórias:  {len(memorias)}")
    print()
    print(f"Estatísticas no Supabase (sala {apelido}):", db.estatisticas(apelido))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python3 migrar_sqlite_para_supabase.py <chat.db> <apelido>")
        raise SystemExit(1)
    if not db.configurado():
        print("Defina SUPABASE_URL e SUPABASE_KEY antes de rodar.")
        raise SystemExit(1)
    migrar(sys.argv[1], sys.argv[2].strip().lower())
