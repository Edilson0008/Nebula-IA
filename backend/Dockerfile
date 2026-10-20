# Nébula — backend (FastAPI + Gemini) + frontend, para hospedar de graça.
#
# Cada pessoa que usa cola a PRÓPRIA chave do Gemini no app, então este
# servidor pode ficar público sem custo nenhum pro dono.
#
# Este contêiner NÃO roda as ferramentas de sistema do agente (terminal,
# compilar APK) — isso só existe no aparelho do dono. Aqui a Nébula é o
# cérebro: conversa, busca, notícias, clima, imagens e geração de arquivos.

# ---------- 1) compila o frontend ----------
FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---------- 2) backend + site pronto ----------
FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
# O site compilado vira ./static e o backend serve em "/".
COPY --from=web /web/dist ./static

ENV WORKSPACE_DIR=/data/workspace
ENV NEBULA_DB_PATH=/data/chat.db
ENV AGENT_SCRATCH_DIR=/tmp/nebula
ENV AGENT_DOWNLOAD_DIR=/tmp/nebula/downloads
ENV AGENT_APK_DIR=/tmp/nebula/apks
ENV FRONTEND_DIST=/app/static
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "mkdir -p /data/workspace /data /tmp/nebula && uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
