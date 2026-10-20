"""Cópia de segurança das conversas (o "cofre").

Antes isto era um arquivo SQLite no disco do servidor, e o cofre só fazia
sentido porque o Render grátis apagava o disco. Agora as conversas moram no
Supabase (permanentes), então o cofre virou o que sempre deveria ter sido:
um **arquivo de reserva** que a pessoa pode baixar e restaurar quando quiser.

Formato da cópia: um JSON (o "pacote .nebula") com as conversas e memórias
daquela sala. O servidor manda/recebe esses bytes em base64, então nada mudou
para o site — só o conteúdo por dentro.

  1. `exportar()`  -> bytes do pacote JSON da sala atual.
  2. `importar(bytes)` -> devolve o pacote para a sala (com validação).
  3. `banco_vazio()` / `estatisticas()` -> resumo da sala atual.
"""

import json

import db_supabase as db

# Limite de sanidade: uma cópia de conversas não passa disso.
TAMANHO_MAX = 64 * 1024 * 1024  # 64 MB


def exportar() -> bytes:
    """Devolve a cópia da sala atual como bytes JSON (pronta para o cofre)."""
    pacote = db.exportar_owner()
    return json.dumps(pacote, ensure_ascii=False).encode("utf-8")


def _validar(dados: bytes) -> dict:
    """Confere que a cópia é da Nébula e devolve o pacote já lido."""
    if not dados:
        raise ValueError("Cópia vazia.")
    if len(dados) > TAMANHO_MAX:
        raise ValueError("Cópia grande demais para restaurar.")

    texto = dados.decode("utf-8", errors="replace").strip()
    if not texto.startswith("{"):
        raise ValueError("O arquivo não é uma cópia da Nébula.")

    try:
        pacote = json.loads(texto)
    except ValueError:
        raise ValueError("O arquivo está corrompido ou não é uma cópia válida.")

    if not isinstance(pacote, dict) or "conversations" not in pacote:
        raise ValueError("O arquivo não é uma cópia da Nébula.")
    return pacote


def importar(dados: bytes) -> dict:
    """Devolve a cópia para a sala atual (após validar)."""
    pacote = _validar(dados)
    return db.importar_owner(pacote)


def banco_vazio() -> bool:
    """True quando a sala atual não tem nenhuma conversa ou memória."""
    return db.banco_vazio()


def estatisticas() -> dict:
    """Resumo da sala atual (para mostrar na tela de segurança)."""
    try:
        return db.estatisticas()
    except Exception:
        return {"conversas": 0, "mensagens": 0, "memorias": 0}
