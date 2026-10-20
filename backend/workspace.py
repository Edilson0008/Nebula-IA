"""Criação e organização dos arquivos que a IA gera.

A IA marca os arquivos no texto usando blocos assim:

    ```file:index.html
    <!doctype html>
    ...
    ```

Este módulo extrai esses blocos, grava os arquivos numa pasta do projeto e
devolve os links para o frontend abrir/baixar.
"""

import os
import re
import time
import unicodedata
from pathlib import Path

DEFAULT_DIR = Path(__file__).parent / "workspace"

# ```file:index.html  ...  ```   (aceita também ```arquivo:)
FILE_BLOCK = re.compile(
    r"```(?:file|arquivo):\s*([^\n`]+?)\s*\n(.*?)(?:```|$)",
    re.DOTALL,
)


def workspace_dir() -> Path:
    """Pasta onde os projetos gerados ficam."""
    raw = os.getenv("WORKSPACE_DIR", "").strip()
    base = Path(raw) if raw else DEFAULT_DIR
    base.mkdir(parents=True, exist_ok=True)
    return base


def extract_files(text: str) -> list[tuple[str, str]]:
    """Acha os blocos ```file:nome ... ``` e devolve [(nome, conteúdo)]."""
    files: list[tuple[str, str]] = []
    for match in FILE_BLOCK.finditer(text):
        name = match.group(1).strip()
        content = match.group(2).strip("\n")
        if name:
            files.append((name, content + "\n"))
    return files


def strip_files(text: str) -> str:
    """Remove os blocos de arquivo (para guardar/analisar só a explicação)."""
    return FILE_BLOCK.sub("", text).strip()


STOPWORDS = {
    "a", "o", "as", "os", "um", "uma", "de", "do", "da", "dos", "das", "em",
    "no", "na", "nos", "nas", "para", "pra", "por", "com", "que", "e", "ou",
    "me", "meu", "minha", "faca", "faz", "crie", "cria", "criar", "monte",
    "monta", "montar", "quero", "queria", "preciso", "gostaria", "por",
    "favor", "sobre", "the", "a", "an", "of", "for", "with", "make", "create",
}


def slugify(text: str) -> str:
    """Transforma um título em um nome de pasta simples e seguro."""
    ascii_text = (
        unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    )
    words = [
        word.lower()
        for word in re.findall(r"[A-Za-z0-9]+", ascii_text)
        if word.lower() not in STOPWORDS
    ]
    slug = "-".join(words)[:32].strip("-")
    return slug or "projeto"


def safe_file(base: Path, name: str) -> Path:
    """Resolve o caminho garantindo que ele fique dentro do projeto."""
    relative = name.replace("\\", "/").lstrip("/")
    base_resolved = base.resolve()
    target = (base_resolved / relative).resolve()
    if target != base_resolved and base_resolved not in target.parents:
        raise ValueError(f"caminho inválido: {name}")
    return target


def project_folder(conversation_id: int, title: str) -> str:
    """Nome da pasta do projeto (criada se ainda não existir)."""
    name = f"{slugify(title)}-{conversation_id}"
    (workspace_dir() / name).mkdir(parents=True, exist_ok=True)
    return name


def write_files(project: str, files: list[tuple[str, str]]) -> list[dict]:
    """Grava os arquivos e devolve nome, url e nº de linhas de cada um."""
    base = workspace_dir() / project
    base.mkdir(parents=True, exist_ok=True)

    written: list[dict] = []
    for name, content in files:
        target = safe_file(base, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        os.chmod(target, 0o644)  # para o gerenciador de arquivos do celular ler
        written.append(
            {
                "name": name,
                "url": f"/files/{project}/{name}",
                "lines": max(content.count("\n"), 1),
            }
        )
    return written


def _image_ext(data: bytes) -> str:
    """Descobre o formato pelo cabeçalho dos bytes (JPEG/PNG/WebP)."""
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return ".png"


def write_image(project: str, data: bytes, mime: str = "image/png") -> dict:
    """Grava uma imagem gerada (PNG/JPEG/WebP) na pasta do projeto."""
    base = workspace_dir() / project
    base.mkdir(parents=True, exist_ok=True)

    ext = _image_ext(data) or {"image/jpeg": ".jpg", "image/webp": ".webp"}.get(
        mime, ".png"
    )
    name = f"imagem-{int(time.time())}{ext}"
    target = base / name
    counter = 1
    while target.exists():  # duas imagens no mesmo segundo
        name = f"imagem-{int(time.time())}-{counter}{ext}"
        target = base / name
        counter += 1

    target.write_bytes(data)
    os.chmod(target, 0o644)  # para o gerenciador de arquivos do celular ler
    return {"name": name, "url": f"/files/{project}/{name}", "lines": 1}



def list_projects() -> list[dict]:
    """Lista os projetos gerados (para o painel de arquivos)."""
    base = workspace_dir()
    projects: list[dict] = []

    for folder in sorted(base.iterdir(), reverse=True):
        if not folder.is_dir():
            continue
        files = sorted(
            str(path.relative_to(folder)).replace(os.sep, "/")
            for path in folder.rglob("*")
            if path.is_file()
        )
        if not files:
            # Pasta criada só para o modelo trabalhar, ainda sem nada dentro.
            continue
        projects.append(
            {
                "project": folder.name,
                "files": [
                    {"name": name, "url": f"/files/{folder.name}/{name}"}
                    for name in files
                ],
            }
        )
    return projects
