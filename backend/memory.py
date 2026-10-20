"""Memória de longo prazo da Nébula.

Guarda fatos sobre o usuário (nome, gostos, projetos, objetivos) e os
recupera por similaridade quando forem relevantes para a pergunta atual.

Os vetores ficam no próprio SQLite (sem serviço externo). Como é uso pessoal,
a busca por similaridade é feita direto em Python — simples e suficiente.
"""

import math
import os
from array import array

import db_supabase as db

DEFAULT_MIN_SCORE = 0.66


def to_blob(vector: list[float]) -> bytes:
    return array("f", vector).tobytes()


def from_blob(blob: bytes) -> list[float]:
    vector = array("f")
    vector.frombytes(blob)
    return list(vector)


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


def add(conversation_id: int, content: str, embedding: list[float]) -> int:
    return db.add_memory(conversation_id, content, to_blob(embedding))


def is_duplicate(embedding: list[float], threshold: float = 0.93) -> bool:
    """Evita guardar o mesmo fato várias vezes."""
    return any(
        cosine(embedding, from_blob(row["embedding"])) >= threshold
        for row in db.all_memories()
    )


def search(
    query_embedding: list[float],
    limit: int = 5,
    min_score: float | None = None,
) -> list[dict]:
    """Fatos mais parecidos com a pergunta atual."""
    if min_score is None:
        try:
            min_score = float(os.getenv("MEMORY_MIN_SCORE", DEFAULT_MIN_SCORE))
        except ValueError:
            min_score = DEFAULT_MIN_SCORE

    scored: list[dict] = []
    for row in db.all_memories():
        score = cosine(query_embedding, from_blob(row["embedding"]))
        if score >= min_score:
            scored.append(
                {"id": row["id"], "content": row["content"], "score": score}
            )

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:limit]
