#!/usr/bin/env bash
# Entrypoint del contenedor Hermes de Tequendama.
# Wirea el workspace montado en /workspace hacia la config global de Hermes:
#  - persona Tequendama (SOUL.md) como identidad global
#  - skills de Tequendama descubribles por Hermes
#  - proveedor DeepSeek desde variables de entorno
# Luego arranca el gateway (WhatsApp) o el modo indicado por HERMES_MODE.
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-/root/.hermes}"
WS=/workspace
HB="$(command -v hermes || echo /root/.hermes/hermes-agent/venv/bin/hermes)"

mkdir -p "$HERMES_HOME/skills"

# 1) Persona global (Tequendama). Respaldamos cualquier SOUL.md previo una sola vez.
if [ -f "$WS/SOUL.md" ]; then
  [ -f "$HERMES_HOME/SOUL.md" ] && [ ! -f "$HERMES_HOME/SOUL.md.orig" ] \
    && cp "$HERMES_HOME/SOUL.md" "$HERMES_HOME/SOUL.md.orig" || true
  cp "$WS/SOUL.md" "$HERMES_HOME/SOUL.md"
fi

# 2) Skills de Tequendama: symlink de cada carpeta al dir global de skills de Hermes.
if [ -d "$WS/skills" ]; then
  for d in "$WS"/skills/*/; do
    name="seguria-$(basename "$d")"
    ln -sfn "$d" "$HERMES_HOME/skills/$name"
  done
fi

# 3) Proveedor DeepSeek (no interactivo) si hay API key.
if [ -n "${DEEPSEEK_API_KEY:-}" ]; then
  grep -q '^DEEPSEEK_API_KEY=' "$HERMES_HOME/.env" 2>/dev/null \
    || echo "DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}" >> "$HERMES_HOME/.env"
  "$HB" config set model.provider deepseek || true
  "$HB" config set model.default "${DEEPSEEK_MODEL:-deepseek-v4-flash}" || true
  # La imagen trae un base_url de OpenRouter que rompe la auth con la key de
  # DeepSeek (401): apúntalo siempre al endpoint oficial.
  "$HB" config set model.base_url "${DEEPSEEK_BASE_URL:-https://api.deepseek.com}" || true
fi

cd "$WS"   # así Hermes lee AGENTS.md del workspace

MODE="${HERMES_MODE:-gateway}"
case "$MODE" in
  gateway)
    # El gateway (WhatsApp) requiere emparejamiento QR la primera vez:
    #   docker compose exec hermes-agent hermes whatsapp
    echo "[hermes] arrancando gateway (WhatsApp). Empareja con: docker compose exec hermes-agent hermes whatsapp"
    exec "$HB" gateway run
    ;;
  idle)
    echo "[hermes] modo idle: contenedor vivo para exec manual (hermes -z '...')."
    exec tail -f /dev/null
    ;;
  *)
    exec "$HB" "$@"
    ;;
esac
