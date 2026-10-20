"""Agente da Nébula — mãos e pernas: arquivos e terminal.

Este módulo dá à IA a capacidade de EXECUTAR tarefas, não só descrevê-las:
ela chama ferramentas em loop (ler, escrever, listar, apagar, executar)
até a tarefa ficar pronta — compilar um APK, instalar dependências com pip/npm,
rodar testes, organizar pastas etc.

Ferramentas
    listar       -> árvore de arquivos da pasta do projeto
    ler          -> conteúdo de um arquivo (linhas numeradas)
    escrever     -> cria/substitui um arquivo no projeto
    criar_pasta  -> cria um diretório no projeto
    apagar       -> apaga arquivo/pasta DO PROJETO
    executar     -> roda um comando bash com cwd no projeto

Travas de segurança (o "igual ao humano, com trava")
    1. Escrita de arquivo só dentro da pasta do projeto (workspace.safe_file).
    2. Arquivos sensíveis (.env, chat.db, chaves SSH) são barrados sempre.
    3. Comandos rodam num ambiente já preparado (Java, Gradle, Android SDK,
       python3, node) e SEM root: não existe sudo/apt para o usuário do
       servidor — a IA usa o que já está instalado ou baixa o que falta.
    4. Comando que toca FORA do projeto (sudo, apt, caminho absoluto
       suspeito, redirecionar para fora, sair com ../...) emite o evento
       "approval" e ESPERA o usuário aprovar no chat. Sem resposta em
       AGENT_APPROVAL_TIMEOUT segundos, é negado.
    5. Comandos destruídos impossíveis (rm -rf /, mkfs, dd of=/dev/...) são
       barrados nem que o usuário queira.

O loop devolve eventos no formato dos SSE do /api/chat/stream:
    {"type": "status", "stage": "thinking"|"tool", "label": "..."}
    {"type": "model",  "model": "gemini-3.8-flash"}
    {"type": "delta",  "text": "..."}
    {"type": "tool",   "phase": "start"|"end"|"progress", "seq": 1,
                       "name": "executar", "detail": "...",
                       "ok": true, "seconds": 12, "note": "..."}
    {"type": "approval", "id": "ab12...", "command": "...",
                         "reason": "instala pacote do sistema"}
    {"type": "error",  "message": "..."}
"""

import os
import json
import re
import shutil
import signal
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Iterator
from pathlib import Path

import workspace
import realtime
import design_guide

# ------------------------------------------------------------------ ajustes

# Teto de passos (chamadas de ferramenta em sequência) por mensagem.
MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "24"))
# Tempo máximo de UM comando (compilação Android de primeira pode demorar).
CMD_TIMEOUT = float(os.getenv("AGENT_CMD_TIMEOUT", "600"))
# Tamanho máximo da saída devolvida ao modelo.
MAX_OUTPUT = int(os.getenv("AGENT_MAX_OUTPUT", "14000"))
# Quanto tempo esperamos o usuário aprovar um comando fora do projeto.
APPROVAL_TIMEOUT = float(os.getenv("AGENT_APPROVAL_TIMEOUT", "120"))
# ask = pergunta no chat | always = roda tudo | never = só dentro do projeto
SHELL_MODE = os.getenv("AGENT_SHELL", "ask").strip().lower()
# Linhas máximas devolvidas pela ferramenta "ler".
READ_MAX_LINES = int(os.getenv("AGENT_READ_LINES", "400"))
# De quanto em quanto tempo avisar que um comando longo está rodando.
PROGRESS_EVERY = float(os.getenv("AGENT_PROGRESS_EVERY", "15"))

# Diretório rápido e gravável fora do /sdcard (caches do Gradle, binários).
# O /sdcard é "noexec" e lento; aqui as ferramentas conseguem rodar de verdade.
SCRATCH = os.getenv("AGENT_SCRATCH_DIR", "/var/lib/nebula")
SDK_DIR = os.getenv("ANDROID_HOME", "/opt/android-sdk")
GRADLE_BIN = "/opt/gradle/bin"
JAVA_CANDIDATES = (
    "/usr/lib/jvm/java-21-openjdk-arm64",
    "/usr/lib/jvm/java-17-openjdk-arm64",
)
# Onde a IA pode deixar um .apk pronto para download SEM precisar de aprovação.
APK_DIR = os.getenv("AGENT_APK_DIR", "/sdcard/Download/nebula-apks")
# APK final: o sistema MESMO copia o .apk compilado pra cá, com o nome do
# projeto — é o arquivo que o usuário instala pelo gerenciador de arquivos,
# sem precisar caçar dentro da pasta do projeto (e sem acumular APK de teste).
DOWNLOAD_DIR = Path(os.getenv("AGENT_DOWNLOAD_DIR", "/sdcard/Download"))

SKIP_DIRS = {".gradle", "__pycache__", "node_modules", ".git"}

# ------------------------------------------------- aprovação de comandos

_APPROVALS: dict[str, tuple[threading.Event, list[bool]]] = {}
_APPROVALS_LOCK = threading.Lock()


def resolve_approval(approval_id: str, approved: bool) -> bool:
    """Ponto do POST /api/approvals: destrava o comando que estava esperando."""
    with _APPROVALS_LOCK:
        entry = _APPROVALS.get(approval_id)
    if entry is None:
        return False  # expirou ou id desconhecido
    event, box = entry
    box.append(approved)
    event.set()
    return True


def _ask_approval(approval_id: str, timeout: float) -> bool:
    """Espera o usuário clicar em Permitir/Negar; sem resposta, nega."""
    with _APPROVALS_LOCK:
        event, box = _APPROVALS.setdefault(approval_id, (threading.Event(), []))
    answered = event.wait(timeout)
    with _APPROVALS_LOCK:
        _APPROVALS.pop(approval_id, None)
    if not answered:
        return False
    return bool(box) and bool(box[0])


# ------------------------------------------------------- análise de comandos

# Caminhos que o comando PODE mencionar sem pedir aprovação (leitura).
_READ_PREFIXES = (
    "/tmp", "/var/lib/nebula", "/opt", "/usr", "/bin", "/sbin", "/lib",
    "/lib64", "/etc", "/dev", "/proc", "/sys", "/system", "/vendor",
    "/product", "/data/local/tmp",
    "/sdcard/Download", "/storage/emulated/0/Download",  # downloads do usuário
    "/sdcard/Download/nebula-projetos", "/sdcard/Download/nebula-apks",
)
# Onde o comando PODE escrever sem aprovação (além da própria pasta do projeto).
_WRITE_OK_EXTRA = ("/tmp", "/var/lib/nebula", "/sdcard/Download/nebula-apks")

# Ninguém lê/apaga estes arquivos, com ou sem aprovação.
_SECRET = re.compile(
    r"(^|[/\s])\.env(\.|$|/)"
    r"|(^|[/\s])chat\.db\b"
    r"|(^|[/\s])id_(rsa|ed25519|ecdsa)\b"
    r"|authorized_keys|(^|[/\s])\.ssh(/|$)"
    r"|(^|[/\s])\.aws(/|$)|(^|[/\s])\.npmrc\b|(^|[/\s])netrc\b",
    re.IGNORECASE,
)

# Comandos que NUNCA rodam, nem com aprovação (destruição irreversível).
_ALWAYS_BLOCKED = [
    (re.compile(r"\brm\s+-[a-zA-Z]*\s+/\s*(\s|;|&|$)"), "apagar a raiz do sistema"),
    (re.compile(r"\bmkfs(\.\w+)?\b"), "formatar disco"),
    (re.compile(r"\bdd\b[^\n]*\bof=/dev/"), "escrever direto no dispositivo"),
    (re.compile(r"\bwipefs\b|\bshred\b"), "apagamento profundo de disco"),
    (re.compile(r":\(\)\s*\{"), "fork bomb"),
    (re.compile(r"\bchmod\s+-R\s+777\s+/\s"), "permissões da raiz inteira"),
    (re.compile(r">\s*/dev/sd[a-z]"), "escrever no disco físico"),
    (re.compile(r"\b(vgremove|pvremove|lvremove|wipefs)\b"), "apagar volume"),
]

# Comandos que PRECISAM de aprovação (foram desenhados para isso).
_NEEDS_APPROVAL = [
    (re.compile(r"(^|\s)sudo\s|(^|\s)su\s+-\s*\w*|(^|\s)doas\s"), "precisa de privilégio de administrador"),
    (re.compile(r"(^|\s)(apt|apt-get|aptitude|dpkg|rpm|snap|flatpak|yum|pacman)\b"),
     "instala pacote do sistema"),
    (re.compile(r"(^|\s)(systemctl|service|initctl|update-rc\.d)\b"),
     "muda serviço do sistema"),
    (re.compile(r"(^|\s)(reboot|shutdown|poweroff|halt|suspend)\b"),
     "desligar/reiniciar o aparelho"),
    (re.compile(r"(^|\s)(killall|pkill|kill|pkill)\b"),
     "matar processos"),
    (re.compile(r"(^|\s)(mount|umount|chroot|crontab|useradd|userdel|groupadd|passwd|visudo|visudo|chown|chgrp|setcap|sysctl)\b"),
     "muda sistema/permissões/usuários"),
    (re.compile(r"(^|\s)(ssh|scp|sftp|rsync\s+[^\n]*:)\b"),
     "acesso remoto"),
    (re.compile(r"\bgit\s+push\b"), "envia código para fora"),
    (re.compile(r"(^|\s)adb\s+(install|uninstall|root|remount|sideload|shell)\b"),
     "instala/algo no aparelho via adb"),
    (re.compile(r"(^|\s)(pipx|poetry\s+config|npm\s+publish|yarn\s+publish)\b"),
     "publica/instala fora do projeto"),
    (re.compile(r"(^|\s)npm\s+(install|i|add)\s+[^\n]*(-g|--global)\b"),
     "instala pacote global"),
    (re.compile(r"\|\s*(sudo\s+)?(ba)?sh\b|\|\s*python3?\b|>\s*/etc/"),
     "passa conteúdo da internet direto pro shell"),
    (re.compile(r"~/|\$HOME|\$\{HOME\}"), "caminho fora do projeto (~ ou $HOME)"),
    (re.compile(r"(^|[\s'\"(=])\.\./"), "sair da pasta do projeto (..)"),
    (re.compile(r"\bpip3?\s+install\b(?![^\n]*venv)"),
     "instala pacote Python fora de um venv do projeto"),
    (re.compile(r"\bcurl\b|\bwget\b"), "baixa arquivo da internet"),
]

# Operações de ESCRITA: se mirarem um caminho fora da área permitida, aí sim
# pede aprovação (leitura de /usr, /etc etc. é normal e não incomoda).
_WRITE_OPS = re.compile(
    r"(^|\s)(rm|mv|cp|mkdir|rmdir|touch|ln|chmod|chown|chgrp|truncate|tee|"
    r"dd|shred|install|unlink|rsync|unzip|tar|python3?|node|sh|bash)\b|>>?\s*[^&]"
)

_ABS_PATH = re.compile(r"(?<![\w~:/.])(/[A-Za-z0-9._+@-]+(?:/[A-Za-z0-9._+@-]+)*)")


def _is_inside(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == p or path.startswith(p.rstrip("/") + "/") for p in prefixes)


def _has_secret(command: str) -> str | None:
    match = _SECRET.search(command)
    return match.group(0).strip() if match else None


def classify_command(command: str, project_dir: Path) -> tuple[str, str]:
    """Devolve ("ok"|"approval"|"blocked", motivo) para um comando."""
    if not command.strip():
        return "blocked", "comando vazio"

    secret = _has_secret(command)
    if secret:
        return "blocked", f"arquivo sensível protegido: {secret}"

    for pattern, why in _ALWAYS_BLOCKED:
        if pattern.search(command):
            return "blocked", f"comando perigoso demais para rodar ({why})"

    # O usuário pode desligar a trava por completo (AGENT_SHELL=always).
    if SHELL_MODE == "always":
        return "ok", ""

    project_prefix = str(project_dir)

    for pattern, why in _NEEDS_APPROVAL:
        if not pattern.search(command):
            continue
        # pip/npm num venv/pasta DO PROJETO é uso interno, não pede aprovação.
        if "venv" in command and why.startswith("instala pacote Python"):
            continue
        if SHELL_MODE == "never":
            return "blocked", f"fora do projeto ({why}) — modo só-dentro-do-projeto"
        return "approval", why

    # Qualquer caminho absoluto precisa estar na área de leitura permitida.
    for match in _ABS_PATH.finditer(command):
        path = match.group(1)
        if _is_inside(path, (project_prefix,)) or _is_inside(path, _READ_PREFIXES):
            # Dentro do permitido para leitura — mas escrever fora é outra história.
            if _WRITE_OPS.search(command) and not _is_inside(
                path, (project_prefix,) + _WRITE_OK_EXTRA
            ):
                if SHELL_MODE == "never":
                    return "blocked", f"escrita fora do projeto: {path}"
                return "approval", f"escreve fora do projeto ({path})"
            continue
        if SHELL_MODE == "never":
            return "blocked", f"caminho fora do projeto: {path}"
        return "approval", f"acessa fora do projeto ({path})"

    # Redirecionamento para caminho fora da área permitida.
    for target in re.findall(r">>{0,1}\s*([^\s;&|]+)", command):
        if target.startswith(("'", '"')):
            target = target.strip("'\"")
        if target.startswith("/"):
            if not _is_inside(target, (project_prefix,) + _WRITE_OK_EXTRA):
                if SHELL_MODE == "never":
                    return "blocked", f"escrita fora do projeto: {target}"
                return "approval", f"escreve fora do projeto ({target})"
        elif target.startswith(("~", "$")):
            return "approval", f"caminho fora do projeto ({target})"

    return "ok", ""


# ------------------------------------------------------------ ambiente/saída


def _command_env() -> dict[str, str]:
    """Ambiente dos comandos: Java + Gradle + Android SDK prontos, SEM root."""
    env = dict(os.environ)
    java = next((path for path in JAVA_CANDIDATES if Path(path).is_dir()), None)
    env.update(
        {
            "HOME": SCRATCH,
            "GRADLE_USER_HOME": f"{SCRATCH}/.gradle",
            "ANDROID_USER_HOME": f"{SCRATCH}/.android",
            "ANDROID_HOME": SDK_DIR,
            "ANDROID_SDK_ROOT": SDK_DIR,
            "TMPDIR": "/tmp",
            "LANG": "C.UTF-8",
        }
    )
    if java:
        env["JAVA_HOME"] = java
    extra = [
        f"{SDK_DIR}/wrappers",  # aapt2/zipalign/adb (x86_64) via emulação qemu
        GRADLE_BIN,
        f"{SDK_DIR}/cmdline-tools/latest/bin",
        f"{SDK_DIR}/platform-tools",
        f"{SDK_DIR}/build-tools/35.0.0",
        f"{SDK_DIR}/build-tools/34.0.0",
    ]
    env["PATH"] = ":".join(extra + [env.get("PATH", "")])
    env["ANDROID_AAPT2_PATH"] = f"{SDK_DIR}/wrappers/aapt2"
    return env


def _clip(text: str, limit: int = MAX_OUTPUT) -> str:
    """Corta a saída pelo MEIO, mantendo começo e fim (é o fim que importa)."""
    if len(text) <= limit:
        return text
    head = limit // 3
    tail = limit - head
    cut = len(text) - tail
    return (
        text[:head]
        + f"\n\n… [{len(text) - limit} caracteres cortados] …\n\n"
        + text[cut:]
    )


# ------------------------------------------------- servidor de teste (fundo)

# Servidor de teste por projeto: sobe em segundo plano (localhost) pra pessoa
# abrir no navegador e ir pedindo ajustes SEM compilar nada. Um por projeto.
_SERVERS: dict[str, subprocess.Popen] = {}
_SERVERS_LOCK = threading.Lock()
SERVER_LOG = ".nebula-servidor.log"

# Registro em disco (pid + comando): se o backend reiniciar no meio do teste,
# ainda dá pra localizar e derrubar o servidor em vez de deixar órfão.
_SERVERS_FILE = Path(SCRATCH) / "nebula-servidores.json"


def _registry() -> dict[str, dict]:
    try:
        data = json.loads(_SERVERS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 - arquivo novo/corrompido = vazio
        return {}


def _registry_save(data: dict[str, dict]) -> None:
    try:
        _SERVERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SERVERS_FILE.write_text(json.dumps(data), encoding="utf-8")
    except Exception:  # noqa: BLE001 - registro é um extra, não essencial
        pass


def _registry_put(project: Path, proc: subprocess.Popen, command: str) -> None:
    data = _registry()
    data[str(project)] = {"pid": proc.pid, "cmd": command}
    _registry_save(data)


def _registry_drop(project: Path) -> None:
    data = _registry()
    if data.pop(str(project), None) is not None:
        _registry_save(data)


def _stored_pid_alive(project: Path) -> int | None:
    """PID do disco que ainda está vivo e é o MESMO comando (PID reciclado)."""
    info = _registry().get(str(project))
    if not info:
        return None
    try:
        pid = int(info.get("pid") or 0)
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    try:
        os.kill(pid, 0)
    except OSError:
        return None
    command = str(info.get("cmd") or "").strip()
    if not command:
        return pid
    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="replace")
    except OSError:
        return None
    return pid if command[:60] in cmdline.replace("\0", " ") else None


def _kill_stored(project: Path) -> bool:
    """Derruba servidor que só existe no registro em disco (reinício do backend)."""
    pid = _stored_pid_alive(project)
    if pid is None:
        _registry_drop(project)
        return False
    # start_new_session=True no start => pgid == pid (mata a árvore inteira).
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pid, sig)
        except OSError:
            try:
                os.kill(pid, sig)
            except OSError:
                _registry_drop(project)
                return True
        for _ in range(20):
            time.sleep(0.15)
            try:
                os.kill(pid, 0)
            except OSError:
                _registry_drop(project)
                return True
    _registry_drop(project)
    return True
_URL_HINT = re.compile(
    r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0)(?::\d{2,5})?(?:/[^\s'\"|]*)?", re.I
)
_PORT_HINT = re.compile(r"\bport\s+(\d{2,5})\b", re.I)


def _server_log_path(project: Path) -> Path:
    return project / SERVER_LOG


def _kill_group(proc: subprocess.Popen) -> None:
    """Derruba o processo e quem ele criou (servidor de teste costuma forkar)."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except Exception:  # noqa: BLE001 - já morreu
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                return
        try:
            proc.wait(timeout=3)
            return
        except Exception:  # noqa: BLE001 - tenta o próximo sinal
            continue


def _server_url(project: Path) -> str:
    """Acha a URL do servidor no log (ou monta pela porta que ele anunciou)."""
    try:
        text = _server_log_path(project).read_text(errors="replace")[-4000:]
    except OSError:
        return ""
    found = _URL_HINT.search(text)
    if found:
        # 0.0.0.0/[::] é endereço de rede, não de navegador: vira localhost.
        return re.sub(r"^https?://(0\.0\.0\.0|\[::\])", "http://localhost",
                      found.group(0), flags=re.I).rstrip("/")
    port = _PORT_HINT.search(text)
    if port:
        return f"http://localhost:{port.group(1)}"
    return ""


def _candidate_ports(command: str) -> list[str]:
    """Portas prováveis citadas no comando (ex.: `http.server 8099`, `-p 3000`)."""
    ports: list[str] = []
    for pattern in (
        r"--port[= ](\d{2,5})",
        r"(?<![\w.])port\s+(\d{2,5})",
        r"(?<![\w.\-])(\d{4,5})(?![\w.])",
    ):
        ports.extend(re.findall(pattern, command))
    seen: list[str] = []
    for port in ports:
        if port not in seen:
            seen.append(port)
    return seen[:6]


def _probe_url(ports: list[str], proc: subprocess.Popen, seconds: float = 7.0) -> str:
    """Confere na prática se alguma porta está servindo e devolve a URL."""
    if not ports:
        return ""
    deadline = time.time() + seconds
    while time.time() < deadline:
        if proc.poll() is not None:
            return ""
        for port in ports:
            url = f"http://localhost:{port}"
            try:
                response = urllib.request.urlopen(f"{url}/", timeout=1)
                response.close()
                return url
            except urllib.error.HTTPError:
                return url  # respondeu com 4xx/5xx: servidor está no ar
            except Exception:  # noqa: BLE001 - porta ainda fechada
                pass
        time.sleep(0.5)
    return ""


def _server_start(project: Path, command: str) -> tuple[bool, str]:
    """Sobe o comando em segundo plano e devolve (ok, recado com a URL)."""
    with _SERVERS_LOCK:
        previous = _SERVERS.pop(str(project), None)
    if previous is not None and previous.poll() is None:
        _kill_group(previous)
    elif _stored_pid_alive(project) is not None:
        _kill_stored(project)  # sobra de um reinício do backend

    try:
        handle = _server_log_path(project).open("a", encoding="utf-8", errors="replace")
    except OSError as exc:
        return False, f"não deu pra abrir o log do servidor: {exc}"
    try:
        handle.write(f"\n$ {command}\n")
        handle.flush()
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=str(project),
            env=_command_env(),
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except OSError as exc:
        handle.close()
        return False, f"não deu pra iniciar o servidor: {exc}"
    finally:
        handle.close()

    with _SERVERS_LOCK:
        _SERVERS[str(project)] = proc
    _registry_put(project, proc, command)

    url = ""
    for _ in range(24):  # ~7s esperando ele anunciar a URL
        time.sleep(0.3)
        if proc.poll() is not None:
            break
        url = _server_url(project)
        if url:
            break

    if proc.poll() is not None:
        try:
            tail = _server_log_path(project).read_text(errors="replace")[-400:]
        except OSError:
            tail = ""
        return False, f"o servidor morreu (exit {proc.returncode}): {tail}"

    if not url:
        # Servidor em silêncio (ex.: http.server do Python 3.13 não anuncia):
        # tenta conectar nas portas citadas no comando e confirma na prática.
        url = _probe_url(_candidate_ports(command), proc, seconds=6.0)

    if url:
        return True, f"servidor de teste no ar: {url} (log: {SERVER_LOG})"
    return True, f"servidor no ar (não achei a URL; veja {SERVER_LOG})"


def _server_status(project: Path) -> tuple[bool, str]:
    with _SERVERS_LOCK:
        proc = _SERVERS.get(str(project))
    if proc is None:
        # Memória vazia (o backend reiniciou): olha o registro em disco.
        pid = _stored_pid_alive(project)
        if pid is None:
            _registry_drop(project)
            return True, "nenhum servidor de teste rodando"
        url = _server_url(project)
        return True, (
            f"servidor de teste rodando (pid {pid}, sobreviveu ao reinício)"
            + (f" em {url}" if url else "")
        )
    code = proc.poll()
    if code is not None:
        _registry_drop(project)
        return True, f"o servidor parou sozinho (exit {code})"
    url = _server_url(project)
    return True, "servidor de teste rodando" + (f" em {url}" if url else "")


def _server_stop(project: Path) -> tuple[bool, str]:
    with _SERVERS_LOCK:
        proc = _SERVERS.pop(str(project), None)
    if proc is not None and proc.poll() is None:
        _kill_group(proc)
        _registry_drop(project)
        return True, "servidor de teste derrubado"
    # Memória vazia ou processo morreu: o registro em disco completa o serviço.
    if _kill_stored(project):
        return True, "servidor de teste derrubado"
    return True, "não havia servidor de teste rodando"


def _realtime(name: str, args: dict) -> tuple[bool, str]:
    """Ferramentas de tempo real (clima/hora/notícias/busca).

    Somente leitura em serviços públicos: sem aprovação, sem efeito colateral.
    Rede fora do ar vira `ok=False` com recado amigável pro modelo repassar.
    """
    try:
        if name == "clima":
            return True, realtime.clima(
                str(args.get("local") or ""), str(args.get("unidade") or "c")
            )
        if name == "hora":
            return True, realtime.hora(str(args.get("fuso") or ""))
        if name == "noticias":
            return True, realtime.noticias(
                str(args.get("tema") or ""), args.get("quantidade") or 5
            )
        if name == "imagens":
            return True, realtime.imagens(
                str(args.get("tema") or ""), args.get("quantidade") or 6
            )
        return True, realtime.buscar(
            str(args.get("consulta") or ""), args.get("quantidade") or 5
        )
    except Exception as exc:  # noqa: BLE001 - timeout, DNS, 5xx, JSON quebrado...
        return False, f"deu ruim em {name}: {exc}"


# --------------------------------------------------------------- ferramentas

TOOLS: list[dict] = [
    {
        "name": "listar",
        "description": (
            "Lista arquivos e pastas de um caminho (relativo ao projeto; "
            "padrão: a raiz do projeto). Use para enxergar o que existe."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "caminho": {
                    "type": "string",
                    "description": "caminho relativo ao projeto, padrão '.'",
                }
            },
            "required": [],
        },
    },
    {
        "name": "ler",
        "description": (
            "Lê um arquivo de texto e devolve as linhas numeradas. "
            "Caminho relativo ao projeto (ou absoluto em /sdcard/Download)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "caminho": {"type": "string"},
                "inicio": {
                    "type": "integer",
                    "description": "primeira linha (1 = início, padrão 1)",
                },
                "linhas": {
                    "type": "integer",
                    "description": "quantas linhas ler no máximo",
                },
            },
            "required": ["caminho"],
        },
    },
    {
        "name": "escrever",
        "description": (
            "Cria ou substitui um arquivo COMPLETO. O caminho é relativo ao "
            "projeto; um caminho ABSOLUTO em /sdcard/Download também vale (o "
            "usuário pede arquivos em Downloads). Sempre envie o conteúdo "
            "inteiro — é assim que o arquivo fica salvo."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "caminho": {
                    "type": "string",
                    "description": "relativo ao projeto, ou absoluto em /sdcard/Download",
                },
                "conteudo": {"type": "string", "description": "conteúdo inteiro do arquivo"},
            },
            "required": ["caminho", "conteudo"],
        },
    },
    {
        "name": "criar_pasta",
        "description": (
            "Cria uma pasta (e as pai, se precisar). Relativa ao projeto, ou "
            "ABSOLUTA dentro de /sdcard/Download (ex.: \"/sdcard/Download/"
            "Nebula ia\"). É assim que se cria uma pasta nos arquivos do "
            "usuário, sem precisar de comando no shell."
        ),
        "parameters": {
            "type": "object",
            "properties": {"caminho": {"type": "string"}},
            "required": ["caminho"],
        },
    },
    {
        "name": "apagar",
        "description": (
            "Apaga um arquivo ou pasta (apaga tudo dentro). Do projeto, ou de "
            "dentro de /sdcard/Download."
        ),
        "parameters": {
            "type": "object",
            "properties": {"caminho": {"type": "string"}},
            "required": ["caminho"],
        },
    },
    {
        "name": "executar",
        "description": (
            "Executa um comando bash com a pasta do projeto como diretório "
            "atual. Use para compilar (gradle assembleDebug), rodar testes, "
            "instalar dependências com pip/npm dentro do projeto, organizar "
            "arquivos, baixar coisas etc. Comandos que tocam FORA do projeto "
            "pedem aprovação do usuário."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "comando": {"type": "string", "description": "o comando bash"}
            },
            "required": ["comando"],
        },
    },
    {
        "name": "servidor",
        "description": (
            "Sobe um SERVIDOR DE TESTE em segundo plano para o usuário ver o "
            "site/app no navegador (localhost) ENQUANTO vocês ajustam o código "
            "— sem compilar nada. acao=iniciar (com `comando`, ex.: "
            "`npm run dev`, `python3 -m http.server 8000`) devolve a URL; "
            "acao=status pergunta se continua no ar; acao=parar derruba. "
            "Só peça o build final DEPOIS que o usuário testar e gostar."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "acao": {
                    "type": "string",
                    "enum": ["iniciar", "status", "parar"],
                    "description": "o que fazer com o servidor",
                },
                "comando": {
                    "type": "string",
                    "description": "comando do servidor (obrigatório em iniciar)",
                },
            },
            "required": ["acao"],
        },
    },
    {
        "name": "clima",
        "description": (
            "Tempo/clima AGORA de uma cidade em tempo real (temperatura, "
            "sensação, umidade, vento + previsão de hoje e amanhã). Use para "
            "qualquer pergunta de clima: \"vai chover?\", \"como está o tempo "
            "em X\", \"temperatura hoje\". Você NÃO sabe o clima de cabeça — "
            "sempre chame esta ferramenta."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "local": {
                    "type": "string",
                    "description": "a cidade, ex.: \"São Paulo\", \"Paris\"",
                },
                "unidade": {
                    "type": "string",
                    "enum": ["c", "f"],
                    "description": "padrão c (Celsius); f = Fahrenheit",
                },
            },
            "required": ["local"],
        },
    },
    {
        "name": "hora",
        "description": (
            "Data e hora ATUAIS em qualquer fuso (Brasil ou exterior). Use "
            "sempre que perguntarem que horas são, que dia é, \"horário em "
            "X\", diferença de fuso etc. fuso aceita apelidos (\"Tóquio\", "
            "\"Nova York\", \"Lisboa\") ou nomes técnicos "
            "(\"America/New_York\"); sem fuso = horário de Brasília."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "fuso": {"type": "string", "description": "cidade/país/fuso (opcional)"}
            },
        },
    },
    {
        "name": "noticias",
        "description": (
            "Manchetes de notícias ATUAIS em português (Google Notícias). "
            "Sem tema = principais notícias do dia; com tema (\"tecnologia\", "
            "\"futebol\", \"eleições\", nome de pessoa/empresa) = notícias "
            "daquele assunto. Use para \"o que aconteceu\", \"notícias de...\"."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tema": {"type": "string", "description": "assunto (opcional)"},
                "quantidade": {"type": "integer", "description": "padrão 5, máx 10"},
            },
        },
    },
    {
        "name": "buscar",
        "description": (
            "Busca na web em TEMPO REAL: resumo quando existe + resultados "
            "com link. Use para fatos atuais que você não pode adivinhar: "
            "preços, versões, lançamentos, campeonatos, \"o que está "
            "acontecendo com X\". Preferível a responder de memória."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "consulta": {"type": "string", "description": "o que procurar"}
            },
            "required": ["consulta"],
        },
    },
    {
        "name": "imagens",
        "description": (
            "Fotos REAIS e livres (Openverse + Wikimedia) que combinam com um "
            "assunto CONCRETO. Use ao criar site/página para pegar URLs de "
            "imagem coerentes, em vez de inventar link, usar URL dinâmica "
            "(picsum/unsplash/placehold) ou foto genérica. Devolve URLs prontas "
            "para <img>. O tema tem de ser um substantivo concreto — o BICHO, o "
            "PRODUTO, o LUGAR (tema=\"leão\", tema=\"pizza\", tema=\"lua\"), NUNCA "
            "adjetivo ou palavra de marketing (\"bem profissional\", \"didático\", "
            "\"incrível\", \"moderno\"): isso não tem foto e volta lixo. Chame uma "
            "vez por assunto de bloco (um card por animal → uma chamada por "
            "animal)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tema": {"type": "string", "description": "assunto das fotos"},
                "quantidade": {"type": "integer", "description": "padrão 6, máx 10"},
            },
            "required": ["tema"],
        },
    },
    {
        "name": "guia",
        "description": (
            "Biblioteca de 300+ agentes especialistas (design, marca, copy, SEO, "
            "engenharia, marketing...). Use ANTES de criar site/app/página ou "
            "quando precisar de um padrão profissional: acao=buscar (acha os "
            "agentes do assunto), acao=ler (abre um agente pelo caminho), "
            "acao=listar (mostra as áreas). É leitura, não altera arquivos."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "acao": {
                    "type": "string",
                    "enum": ["buscar", "ler", "listar"],
                    "description": "o que fazer na biblioteca",
                },
                "consulta": {
                    "type": "string",
                    "description": "assunto (em buscar) ou caminho do agente (em ler)",
                },
            },
            "required": ["acao"],
        },
    },
]

TOOL_LABELS = {
    "listar": "Listando arquivos",
    "ler": "Lendo",
    "escrever": "Escrevendo",
    "criar_pasta": "Criando pasta",
    "apagar": "Apagando",
    "executar": "Executando comando",
    "servidor": "Servidor de teste",
    "clima": "Consultando o clima",
    "hora": "Checando a hora",
    "noticias": "Lendo notícias",
    "buscar": "Buscando na web",
    "imagens": "Buscando fotos",
    "guia": "Consultando o manual de design",
}


# Áreas extras onde a IA pode MEXER EM ARQUIVO sem pedir aprovação: a pasta de
# Downloads do aparelho (e subpastas). O usuário pede coisas do tipo "crie a
# pasta Nebula ia em Downloads" — sem isto, `criar_pasta`/`escrever` recusavam
# na hora ("caminho fora do projeto") e o pedido nunca saía do papel.
# A pasta do projeto continua valendo sempre; estas são um adicional.
def _extra_roots() -> tuple[Path, ...]:
    raizes = [DOWNLOAD_DIR]
    for bruto in os.getenv("AGENT_EXTRA_ROOTS", "").split(":"):
        if bruto.strip():
            raizes.append(Path(bruto.strip()))
    return tuple(sorted({r.resolve() for r in raizes}, key=str))


def _safe_path(project: Path, name: str) -> Path:
    """Caminho dentro do projeto (ou de uma área permitida); fora, recusa.

    Aceita caminho relativo (resolvido contra o projeto) e caminho ABSOLUTO que
    caia na pasta do projeto ou numa área extra liberada (Downloads). Qualquer
    outro destino continua recusado — a trava segue de pé, só o alvo mudou.
    """
    cleaned = str(name or "").strip().replace("\\", "/")
    if not cleaned:
        raise ValueError("caminho vazio")
    if _SECRET.search(cleaned):
        raise ValueError(f"arquivo protegido: {cleaned}")
    # ".." não entra: subir de pasta é como se escapa da área permitida. O
    # shell já recusa; as ferramentas de arquivo têm de recusar igual.
    if re.search(r"(^|/)\.\.(/|$)", cleaned):
        raise ValueError(f"caminho com '..' não é aceito: {name}")
    base = project.resolve()
    raizes = (base, *_extra_roots())
    alvo = Path(cleaned).expanduser()
    if alvo.is_absolute():
        target = alvo.resolve()
    else:
        target = (base / cleaned.lstrip("/")).resolve()
    if not _inside_any(target, raizes):
        raise ValueError(f"caminho fora do projeto: {name}")
    return target


def _inside_any(target: Path, raizes: tuple[Path, ...]) -> bool:
    return any(target == r or r in target.parents for r in raizes)


def _tool_listar(project: Path, args: dict) -> tuple[bool, str]:
    relative = str(args.get("caminho") or ".").strip() or "."
    base = _safe_path(project, relative)
    if not base.exists():
        return False, f"não existe: {relative}"
    if base.is_file():
        return True, f"{relative}  ({base.stat().st_size} bytes)"

    lines: list[str] = []
    count = 0
    for path in sorted(base.rglob("*")):
        rel = str(path.relative_to(base)).replace(os.sep, "/")
        parts = rel.split("/")
        if any(part in SKIP_DIRS for part in parts):
            continue
        if path.is_dir():
            continue
        size = path.stat().st_size
        lines.append(f"{rel}  ({size} bytes)")
        count += 1
        if count >= 400:
            lines.append("… (mais arquivos omitidos)")
            break
    if not lines:
        return True, f"{relative}: pasta vazia"
    return True, "\n".join(lines)


def _tool_ler(project: Path, args: dict) -> tuple[bool, str]:
    name = str(args.get("caminho") or "")
    target = _safe_path(project, name)
    if not target.exists():
        return False, f"não existe: {name}"
    if target.is_dir():
        return False, f"{name} é uma pasta (use listar)"
    size = target.stat().st_size
    if size > 4_000_000:
        return False, f"arquivo grande demais ({size} bytes) — use executar com um recorte"
    try:
        raw = target.read_bytes()
    except OSError as exc:
        return False, f"não deu para ler: {exc}"
    if b"\x00" in raw[:4096]:
        return False, f"{name} parece binário ({size} bytes)"
    text = raw.decode("utf-8", errors="replace")

    start = max(int(args.get("inicio") or 1), 1)
    wanted = int(args.get("linhas") or READ_MAX_LINES)
    wanted = max(1, min(wanted, READ_MAX_LINES))

    lines = text.splitlines()
    chunk = lines[start - 1 : start - 1 + wanted]
    numbered = "\n".join(
        f"{start + i:5d}| {line}" for i, line in enumerate(chunk)
    )
    out = numbered or "(arquivo vazio)"
    truncated = ""
    if start - 1 + len(chunk) < len(lines):
        truncated = f"\n… (mais {len(lines) - start + 1 - len(chunk)} linhas; peça com 'inicio' maior)"
    return True, _clip(out + truncated, 60_000)


def _tool_escrever(project: Path, args: dict, state: "AgentState") -> tuple[bool, str]:
    name = str(args.get("caminho") or "")
    content = args.get("conteudo")
    if content is None:
        return False, "conteúdo vazio"
    content = str(content)
    target = _safe_path(project, name)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    try:
        os.chmod(target, 0o644)
    except OSError:
        pass
    rel = _rel_label(target, project)
    lines = max(content.count("\n"), 1)
    if not any(item["name"] == rel for item in state.files):
        state.files.append({"name": rel, "url": "", "lines": lines})
    return True, f"salvo: {rel} ({lines} linhas, {len(content)} bytes)"


def _rel_label(target: Path, project: Path) -> str:
    """Rótulo do arquivo para o chat: relativo ao projeto ou à área liberada.

    Arquivo fora do projeto (Downloads) não tem "relativo ao projeto" — usar
    `relative_to` estouraria. Aí mostramos o caminho absoluto, que é o que o
    usuário precisa para achar o arquivo.
    """
    try:
        return str(target.relative_to(project.resolve())).replace(os.sep, "/")
    except ValueError:
        return str(target)


def _tool_criar_pasta(project: Path, args: dict) -> tuple[bool, str]:
    name = str(args.get("caminho") or "")
    target = _safe_path(project, name)
    target.mkdir(parents=True, exist_ok=True)
    return True, f"pasta criada: {name}"


def _tool_apagar(project: Path, args: dict, state: "AgentState") -> tuple[bool, str]:
    name = str(args.get("caminho") or "")
    target = _safe_path(project, name)
    if not target.exists():
        return False, f"não existe: {name}"
    if target == project.resolve() or target in _extra_roots():
        return False, "não dá para apagar uma pasta de área liberada inteira"
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    removed = _rel_label(target, project)
    state.files = [
        item for item in state.files if not item["name"].startswith(removed)
    ]
    return True, f"apagado: {removed}"


def _run_command(
    command: str, project: Path, seq: int
) -> Iterator[dict]:
    """Roda um comando; rende eventos de progresso e devolve (ok, nota, saída)."""
    started = time.time()
    env = _command_env()
    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=str(project),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            bufsize=1,
            start_new_session=True,
        )
    except OSError as exc:
        return False, f"não deu para iniciar: {exc}", ""

    captured: list[str] = []
    overflow = [0]

    def _drain() -> None:
        try:
            for line in proc.stdout:  # type: ignore[union-attr]
                if sum(len(x) for x in captured) < MAX_OUTPUT * 2:
                    captured.append(line)
                else:
                    overflow[0] += len(line)
        except Exception:  # noqa: BLE001 - saída pode fechar no kill
            pass

    reader = threading.Thread(target=_drain, daemon=True)
    reader.start()

    last_progress = started
    timed_out = False
    while proc.poll() is None:
        time.sleep(0.4)
        now = time.time()
        if now - started > CMD_TIMEOUT:
            timed_out = True
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except OSError:
                proc.kill()
            break
        if now - last_progress >= PROGRESS_EVERY:
            last_progress = now
            last_line = (captured[-1].strip() if captured else "")[:200]
            yield {
                "type": "tool",
                "phase": "progress",
                "seq": seq,
                "seconds": int(now - started),
                "note": last_line,
            }

    reader.join(timeout=2)
    proc.wait(timeout=5)
    seconds = int(time.time() - started)
    output = "".join(captured)
    if overflow[0]:
        output += f"\n… [{overflow[0]} bytes extras cortados]"
    output = _clip(output.strip() or "(sem saída)")

    if timed_out:
        return False, f"tempo esgotado ({int(CMD_TIMEOUT)}s)", output
    code = proc.returncode
    note = f"exit {code}" if code == 0 else f"exit {code} (falhou)"
    return code == 0, note, output


# ------------------------------------------------------------ estado/loop


class AgentState:
    """O que o agente devolve para o chamador (fora dos eventos)."""

    def __init__(self, project: str):
        self.project = project
        self.files: list[dict] = []
        self.downloads: list[str] = []
        self.model: str | None = None
        self.steps = 0
        self.finished = False

    def collect_artifacts(self, project_dir: Path) -> list[dict]:
        """Procura .apk/.aab/.ipa gerados e monta os cartões de download."""
        found: list[dict] = []
        apks: list[Path] = []
        for pattern in ("*.apk", "*.aab", "*.xapk"):
            for path in sorted(project_dir.rglob(pattern)):
                if any(part in SKIP_DIRS for part in path.parts):
                    continue
                rel = str(path.relative_to(project_dir)).replace(os.sep, "/")
                if any(item["name"] == rel for item in self.files):
                    continue
                self.files.append(
                    {
                        "name": rel,
                        "url": f"/files/{self.project}/{rel}",
                        "lines": 1,
                    }
                )
                found.append(rel)
                # Instalável de verdade: ignora o intermediário (não assinado).
                if pattern == "*.apk" and "intermediates" not in path.parts:
                    apks.append(path)
        # Copia o APK final pra /sdcard/Download/<projeto>.apk (sobrescreve,
        # então rebuild = mesm arquivo atualizado, sem acumular lixo).
        if apks:
            principal = max(
                apks, key=lambda p: p.stat().st_size if p.exists() else 0
            )
            copia = _copy_apk_to_download(principal, self.project)
            if copia:
                self.downloads.append(copia)
        return found


def _copy_apk_to_download(apk: Path, project: str) -> str:
    """Leva o .apk final pra /sdcard/Download com o nome do projeto."""
    try:
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        destino = DOWNLOAD_DIR / f"{project or 'app'}.apk"
        shutil.copy2(apk, destino)
        return str(destino)
    except OSError:
        return ""


def _detail(name: str, args: dict) -> str:
    if name == "executar":
        return str(args.get("comando", ""))[:160]
    if name == "servidor":
        acao = str(args.get("acao", "iniciar"))
        if acao == "iniciar":
            return f"iniciar: {str(args.get('comando', ''))[:140]}"
        return acao
    if name == "clima":
        return str(args.get("local", ""))[:120]
    if name == "hora":
        return str(args.get("fuso") or "Brasília")[:80]
    if name == "noticias":
        return str(args.get("tema") or "principais notícias")[:120]
    if name == "buscar":
        return str(args.get("consulta", ""))[:160]
    if name == "imagens":
        return str(args.get("tema", ""))[:120]
    if name == "guia":
        return str(args.get("consulta") or args.get("acao") or "")[:120]
    if name in ("ler", "listar", "criar_pasta", "apagar"):
        return str(args.get("caminho", "."))[:160]
    if name == "escrever":
        content = str(args.get("conteudo") or "")
        return f"{args.get('caminho', '?')}  ({len(content)} bytes)"
    return str(args)[:160]


def _build_contents(
    history: list[dict], message: str, attachments: list[dict] | None
) -> list[dict]:
    contents: list[dict] = [
        {"role": m["role"], "parts": [{"text": m["content"]}]} for m in history
    ]
    parts: list[dict] = [{"text": message or "Analise o anexo enviado."}]
    for item in attachments or []:
        parts.append(
            {
                "inline_data": {
                    "mime_type": item["mime_type"],
                    "data": item["data"],
                }
            }
        )
    contents.append({"role": "user", "parts": parts})
    return contents


def _chunked(text: str, size: int = 700) -> Iterator[str]:
    for start in range(0, len(text), size):
        yield text[start : start + size]


def run(
    client,
    system: str,
    history: list[dict],
    message: str,
    attachments: list[dict] | None,
    project: str,
    state: AgentState,
    thinking_budget: int = 0,
) -> Iterator[dict]:
    """Laço do agente: pensa -> chama ferramenta -> repete até terminar."""
    project_dir = workspace.workspace_dir() / project
    project_dir.mkdir(parents=True, exist_ok=True)
    try:
        Path(SCRATCH).mkdir(parents=True, exist_ok=True)
        Path(APK_DIR).mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    contents = _build_contents(history, message, attachments)
    seq = 0

    for step in range(1, MAX_STEPS + 1):
        state.steps = step
        yield {"type": "status", "stage": "thinking", "label": "Pensando"}
        try:
            result = client.tool_step(system, contents, TOOLS, thinking_budget=thinking_budget)
        except Exception as exc:  # noqa: BLE001 - repassa como erro amigável
            yield {"type": "error", "message": str(exc)[:400], "kind": "error"}
            return

        if result.get("model"):
            state.model = result["model"]

        text = (result.get("text") or "").strip()
        calls = result.get("calls") or []

        if text:
            for piece in _chunked(text):
                yield {"type": "delta", "text": piece}

        if not calls:
            state.finished = True
            break

        # Executa cada ferramenta pedida neste passo.
        responses: list[dict] = []
        for call in calls:
            name = str(call.get("name") or "")
            args = call.get("args") or {}
            seq += 1
            ok = True
            note = ""
            payload: str = ""

            if name not in {tool["name"] for tool in TOOLS}:
                ok, note = False, f"ferramenta desconhecida: {name}"
                payload = note
                yield {"type": "tool", "phase": "start", "seq": seq,
                       "name": name, "detail": "?"}
                yield {"type": "tool", "phase": "end", "seq": seq, "name": name,
                       "detail": "?", "ok": False, "seconds": 0, "note": note}
                responses.append({"name": name, "response": {"ok": False, "resultado": note}})
                continue

            detail = _detail(name, args)
            yield {"type": "status", "stage": "tool", "label": TOOL_LABELS.get(name, "Trabalhando")}
            yield {"type": "tool", "phase": "start", "seq": seq, "name": name, "detail": detail}

            started = time.time()
            progress: list[dict] = []

            try:
                if name == "executar":
                    command = str(args.get("comando") or "").strip()
                    mode, reason = classify_command(command, project_dir)

                    if mode == "blocked":
                        ok = False
                        note = f"negado: {reason}"
                        payload = note
                    elif mode == "approval":
                        approval_id = uuid.uuid4().hex[:12]
                        yield {
                            "type": "approval",
                            "id": approval_id,
                            "command": command,
                            "reason": reason,
                            "seq": seq,
                        }
                        yield {
                            "type": "tool",
                            "phase": "progress",
                            "seq": seq,
                            "note": "aguardando aprovação…",
                        }
                        if _ask_approval(approval_id, APPROVAL_TIMEOUT):
                            approved_note = "aprovado pelo usuário; "
                            ok, note, payload = yield from _run_command(
                                command, project_dir, seq
                            )
                            note = approved_note + note
                        else:
                            ok = False
                            note = "o usuário NÃO aprovou este comando"
                            payload = note
                    else:
                        ok, note, payload = yield from _run_command(
                            command, project_dir, seq
                        )
                elif name == "servidor":
                    acao = str(args.get("acao") or "iniciar").strip().lower()
                    if acao == "parar":
                        ok, payload = _server_stop(project_dir)
                        note = payload[:200]
                    elif acao == "status":
                        ok, payload = _server_status(project_dir)
                        note = payload[:200]
                    else:
                        command = str(args.get("comando") or "").strip()
                        if not command:
                            ok = False
                            note = "falta o `comando` do servidor"
                            payload = note
                        else:
                            mode, reason = classify_command(command, project_dir)
                            if mode == "blocked":
                                ok = False
                                note = f"negado: {reason}"
                                payload = note
                            else:
                                allowed = True
                                if mode == "approval":
                                    approval_id = uuid.uuid4().hex[:12]
                                    yield {
                                        "type": "approval",
                                        "id": approval_id,
                                        "command": command,
                                        "reason": reason,
                                        "seq": seq,
                                    }
                                    yield {
                                        "type": "tool",
                                        "phase": "progress",
                                        "seq": seq,
                                        "note": "aguardando aprovação…",
                                    }
                                    allowed = _ask_approval(
                                        approval_id, APPROVAL_TIMEOUT
                                    )
                                    if not allowed:
                                        ok = False
                                        note = "o usuário NÃO aprovou o servidor"
                                        payload = note
                                if allowed:
                                    ok, payload = _server_start(project_dir, command)
                                    note = payload[:200]
                elif name in ("clima", "hora", "noticias", "buscar", "imagens"):
                    # Tempo real: só leitura, rede pública — sem aprovação.
                    ok, payload = _realtime(name, args)
                    note = "ok" if ok else payload[:200]
                elif name == "guia":
                    acao = str(args.get("acao") or "buscar").strip().lower()
                    if acao == "listar":
                        payload = design_guide.listar()
                    elif acao == "ler":
                        payload = design_guide.ler(str(args.get("consulta") or ""))
                    else:
                        payload = design_guide.buscar(str(args.get("consulta") or ""))
                    ok = True
                    note = "ok"
                elif name == "listar":
                    ok, payload = _tool_listar(project_dir, args)
                    note = "ok" if ok else payload[:200]
                elif name == "ler":
                    ok, payload = _tool_ler(project_dir, args)
                    note = "ok" if ok else payload[:200]
                elif name == "escrever":
                    ok, payload = _tool_escrever(project_dir, args, state)
                    note = "ok" if ok else payload[:200]
                elif name == "criar_pasta":
                    ok, payload = _tool_criar_pasta(project_dir, args)
                    note = "ok" if ok else payload[:200]
                elif name == "apagar":
                    ok, payload = _tool_apagar(project_dir, args, state)
                    note = "ok" if ok else payload[:200]
            except ValueError as exc:
                ok, note = False, str(exc)
                payload = note
            except OSError as exc:
                ok, note = False, f"erro de arquivo: {exc}"
                payload = note
            except Exception as exc:  # noqa: BLE001 - nunca derruba o laço
                ok, note = False, f"falha: {exc}"
                payload = note

            seconds = int(time.time() - started)
            yield {
                "type": "tool",
                "phase": "end",
                "seq": seq,
                "name": name,
                "detail": detail,
                "ok": ok,
                "seconds": seconds,
                "note": str(note)[:300],
            }
            responses.append(
                {
                    "name": name,
                    "response": {"ok": ok, "resultado": str(payload)[:MAX_OUTPUT]},
                }
            )

        # Devolve o resultado das ferramentas para o modelo continuar.
        # Prioriza as partes CRUAS da resposta (com thought_signature — com
        # thinking ligado a API exige a assinatura de volta senão dá 400).
        raw_parts = result.get("parts") or []
        model_parts = []
        response_parts = []
        for call, response in zip(calls, responses):
            fc: dict = {
                "name": str(call.get("name")),
                "args": call.get("args") or {},
            }
            if call.get("id"):
                fc["id"] = call["id"]
            model_parts.append({"function_call": fc})
            fr: dict = {"name": fc["name"], "response": response["response"]}
            if call.get("id"):
                fr["id"] = call["id"]
            response_parts.append({"function_response": fr})

        contents.append({"role": "model", "parts": raw_parts or model_parts})
        contents.append({"role": "user", "parts": response_parts})

    state.collect_artifacts(project_dir)

    if state.downloads:
        yield {
            "type": "delta",
            "text": "\n\n📱 Deixei o APK final na pasta **Download** do celular: `"
            + ", ".join(state.downloads)
            + "` — é só abrir o Gerenciador de arquivos e instalar.",
        }

    if not state.finished:
        yield {
            "type": "delta",
            "text": "\n\n⚠️ Parei no limite de passos da tarefa. Envie de novo "
            "que eu continuo de onde parei.",
        }
