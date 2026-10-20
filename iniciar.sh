#!/usr/bin/env bash
# Inicia a Nébula (backend + frontend) neste Android/Termux.
#
# POR QUE NÃO RODA DIRETO DA PASTA DO DOWNLOAD?
#   A pasta /sdcard é montada como "noexec" (o Android proíbe executar
#   programas de lá). O Python (venv) e o Vite (esbuild/Tailwind) precisam
#   EXECUTAR arquivos, então eles ficam no armazenamento interno (/root).
#   O código-fonte continua aqui na pasta do Download: um sincronizador copia
#   suas edições do frontend para a cópia que roda, então elas aparecem na hora.
#
# USO:   bash iniciar.sh          (sobe tudo)
#        bash iniciar.sh parar    (derruba tudo)

set -u

PROJ="/storage/emulated/0/Download/minha-ia"
BACK="$PROJ/backend"
FRONT_REAL="$PROJ/frontend"

VENV="/root/nebula-venv"          # Python + FastAPI (roda de /root)
FRONT_RUN="/root/nebula-frontend" # cópia executável do frontend
SYNC="/root/sync-frontend.sh"
PORTA_BACK=8000
PORTA_FRONT=5173

parar() {
  echo "Parando a Nébula..."
  pkill -f "[u]vicorn main:app" 2>/dev/null
  pkill -f "[v]ite.js" 2>/dev/null
  pkill -f "[s]ync-frontend.sh" 2>/dev/null
  echo "Parado."
}

if [ "${1:-}" = "parar" ] || [ "${1:-}" = "stop" ]; then
  parar
  exit 0
fi

# --- 1. Backend: ambiente Python (só na primeira vez) ---
if [ ! -x "$VENV/bin/python" ]; then
  echo "[1/4] Criando o ambiente Python (primeira vez)..."
  python3 -m venv "$VENV" || { echo "Falhou. Rode antes: apt-get install -y python3.13-venv"; exit 1; }
  "$VENV/bin/pip" install -q -r "$BACK/requirements.txt" || { echo "Falhou o pip install."; exit 1; }
fi

# --- 2. Frontend: cópia executável (só na primeira vez) ---
if [ ! -d "$FRONT_RUN/node_modules" ]; then
  echo "[2/4] Preparando o frontend (primeira vez)..."
  mkdir -p "$FRONT_RUN"
  ( cd "$FRONT_REAL" && tar --exclude=node_modules --exclude=.git -cf - . ) | ( cd "$FRONT_RUN" && tar -xf - )
  ( cd "$FRONT_RUN" && npm install --no-audit --no-fund --cache /root/.npm-nebula ) || { echo "Falhou o npm install."; exit 1; }
fi

# --- 3. Derruba o que sobrou de uma execução anterior ---
parar >/dev/null 2>&1
sleep 1

# --- 4. Sincronizador: edita no Download -> aparece no app ---
cat > "$SYNC" <<'SYNCEOF'
#!/usr/bin/env bash
SRC="/storage/emulated/0/Download/minha-ia/frontend"
DST="/root/nebula-frontend"
while true; do
  cp -ru "$SRC/src/." "$DST/src/" 2>/dev/null
  if [ -d "$SRC/public" ]; then
    mkdir -p "$DST/public" 2>/dev/null
    cp -ru "$SRC/public/." "$DST/public/" 2>/dev/null
  fi
  for f in index.html vite.config.ts tsconfig.json package.json; do
    [ -f "$SRC/$f" ] && cp -u "$SRC/$f" "$DST/$f" 2>/dev/null
  done
  sleep 2
done
SYNCEOF
chmod +x "$SYNC"
if ! pgrep -f "[s]ync-frontend.sh" >/dev/null 2>&1; then
  setsid nohup "$SYNC" > /root/sync-frontend.log 2>&1 < /dev/null &
fi

# --- 5. Sobe tudo ---
echo "[3/4] Subindo o backend..."
( cd "$BACK" && setsid nohup "$VENV/bin/python" -m uvicorn main:app --host 127.0.0.1 --port "$PORTA_BACK" > /root/backend.log 2>&1 < /dev/null & )

echo "[4/4] Subindo o frontend..."
( cd "$FRONT_RUN" && setsid nohup node ./node_modules/vite/bin/vite.js --host 127.0.0.1 --port "$PORTA_FRONT" > /root/frontend.log 2>&1 < /dev/null & )

sleep 6

if curl -s -m 3 -o /dev/null "http://127.0.0.1:$PORTA_FRONT/"; then
  echo
  echo "Nébula no ar  ->  abra: http://localhost:$PORTA_FRONT"
  echo "Logs: /root/backend.log  e  /root/frontend.log"
  echo "Para parar: bash iniciar.sh parar"
else
  echo
  echo "Algo não subiu. Veja o erro:"
  tail -n 15 /root/frontend.log
  tail -n 15 /root/backend.log
  exit 1
fi
