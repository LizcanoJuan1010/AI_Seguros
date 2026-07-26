#!/usr/bin/env bash
# Setup de Tequendama: API + (opcional) Hermes, OfficeCLI y voz (Kokoro).
# Uso: bash scripts/setup.sh [api|hermes|officecli|voz|docker|all]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${1:-api}"

setup_api() {
  echo "==> Tequendama API (FastAPI + SQLite)"
  cd "$ROOT/apps/ai"
  command -v uv >/dev/null || { echo "Instala uv: https://docs.astral.sh/uv/"; exit 1; }
  uv venv .venv 2>/dev/null || true
  uv pip install -r requirements.txt --python .venv/bin/python
  echo "OK. Arranca con: cd apps/ai && .venv/bin/uvicorn app.main:app --port 8085"
}

setup_hermes() {
  echo "==> Hermes Agent (NousResearch)"
  command -v hermes >/dev/null || curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
  echo "Luego: cd services/hermes-agent && hermes   (config en services/hermes-agent/README.md)"
}

setup_officecli() {
  echo "==> OfficeCLI (presentaciones/documentos) — binario: officecli"
  command -v officecli >/dev/null || curl -fsSL https://raw.githubusercontent.com/iOfficeAI/OfficeCLI/main/install.sh | bash
  officecli --version || true
}

setup_voz() {
  echo "==> Voz: Kokoro-FastAPI (TTS local en español, API OpenAI-compatible en :8880)"
  command -v docker >/dev/null || { echo "Requiere Docker"; return 1; }
  docker run -d --name seguria-tts --restart unless-stopped \
    -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest || true
  echo "Prueba: curl -s localhost:8880/v1/audio/voices | head"
}

setup_docker() {
  echo "==> Stack completo con Docker Compose"
  [ -f "$ROOT/.env" ] || cp "$ROOT/.env.example" "$ROOT/.env"
  echo "Edita $ROOT/.env (DEEPSEEK_API_KEY, MANAGER_PHONES) y ejecuta:"
  echo "  docker compose up -d --build"
}

case "$TARGET" in
  api) setup_api ;;
  hermes) setup_hermes ;;
  officecli) setup_officecli ;;
  voz) setup_voz ;;
  docker) setup_docker ;;
  all) setup_api; setup_hermes; setup_officecli; setup_voz ;;
  *) echo "Uso: $0 [api|hermes|officecli|voz|docker|all]"; exit 1 ;;
esac
