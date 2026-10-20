"""Cópia de segurança das conversas quando o servidor é gratuito.

O plano grátis do Render apaga o disco a cada reinício. Para não perder o
histórico, a Nébula guarda um "cofre" (backup) que fica FORA do servidor:

  - LOCAL (celular do dono): uma cópia em /sdcard/Download.
  - NUVEM (deploy grátis): o servidor também pode mandar a cópia para um
    endereço externo, ou o próprio navegador guarda e devolve.

Como funciona:
  1. `exportar()` devolve os bytes do banco (sqlite) de forma consistente.
  2. `importar(bytes)` substitui o banco atual pela cópia, com validação —
     só aceita um SQLite de verdade com as tabelas da Nébula.
  3. `precisa_restaurar()` diz se o banco está vazio (típico após reinício).

A cópia é feita pelo próprio SQLite (`Connection.backup`), que é seguro mesmo
com o banco em uso — não há risco de pegar um arquivo pela metade.
"""

import io
import sqlite3
from pathlib import Path

import db

# Limite de sanidade: um cofre de conversas não passa disso (evita upload gigante).
TAMANHO_MAX = 64 * 1024 * 1024  # 64 MB

# Tabelas que provam que o arquivo é da Nébula (e não qualquer SQLite).
TABELAS_ESPERADAS = {"conversations", "messages", "memories"}


def _magic_ok(dados: bytes) -> bool:
    """Todo banco SQLite começa com esta assinatura."""
    return dados[:16] == b"SQLite format 3\x00"


def exportar() -> bytes:
    """Devolve o banco inteiro como bytes, de forma consistente.

    Usa o backup nativo do SQLite: copia a base em uso sem travar e sem
    risco de capturar uma escrita pela metade.
    """
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp:
        caminho = temp.name
    try:
        origem = sqlite3.connect(db.DB_PATH)
        destino = sqlite3.connect(caminho)
        try:
            origem.backup(destino)
        finally:
            destino.close()
            origem.close()
        dados = Path(caminho).read_bytes()
    finally:
        try:
            Path(caminho).unlink()
        except OSError:
            pass
    return dados


def _validar(dados: bytes) -> None:
    if not dados:
        raise ValueError("Cópia vazia.")
    if len(dados) > TAMANHO_MAX:
        raise ValueError("Cópia grande demais para restaurar.")
    if not _magic_ok(dados):
        raise ValueError("O arquivo não é um banco da Nébula.")
    # Confere que as tabelas existem (senão seria outro SQLite qualquer).
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp:
        caminho = temp.name
        temp.write(dados)
    try:
        test = sqlite3.connect(caminho)
        try:
            nomes = {
                linha[0]
                for linha in test.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        finally:
            test.close()
    except sqlite3.DatabaseError:
        raise ValueError("O arquivo está corrompido ou não é um banco válido.")
    finally:
        try:
            Path(caminho).unlink()
        except OSError:
            pass
    if not TABELAS_ESPERADAS.issubset(nomes):
        raise ValueError("O banco não tem as tabelas da Nébula.")


def importar(dados: bytes) -> None:
    """Substitui o banco atual pela cópia enviada (após validar)."""
    _validar(dados)
    caminho = Path(db.DB_PATH)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    # Grava num arquivo temporário e troca de uma vez (atômico).
    temp = caminho.with_suffix(".restore")
    temp.write_bytes(dados)
    temp.replace(caminho)


def banco_vazio() -> bool:
    """True quando não há nenhuma conversa salva (banco novo/apagado)."""
    try:
        with db._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            total += conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        return total == 0
    except Exception:
        return True


def estatisticas() -> dict:
    """Resumo do que existe hoje (para mostrar na tela de segurança)."""
    try:
        with db._connect() as conn:
            conversas = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            mensagens = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            memorias = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        return {
            "conversas": conversas,
            "mensagens": mensagens,
            "memorias": memorias,
        }
    except Exception:
        return {"conversas": 0, "mensagens": 0, "memorias": 0}
