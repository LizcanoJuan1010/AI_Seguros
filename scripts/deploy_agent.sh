#!/usr/bin/env bash
# Cablea el workspace Tequendama a la instalación nativa de Hermes, de forma idempotente
# y NO destructiva (respalda lo que sobrescribe). No toca tu API key.
# Uso: bash scripts/deploy_agent.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AGENT="$ROOT/services/hermes-agent"
HH="${HERMES_HOME:-$HOME/.hermes}"

command -v hermes >/dev/null || { echo "Hermes no está instalado. Ejecuta: bash scripts/setup.sh hermes"; exit 1; }
mkdir -p "$HH/skills"

echo "==> Persona Tequendama -> $HH/SOUL.md"
if [ -f "$HH/SOUL.md" ] && [ ! -f "$HH/SOUL.md.orig" ]; then
  cp "$HH/SOUL.md" "$HH/SOUL.md.orig"
  echo "   (respaldo del SOUL.md previo en SOUL.md.orig)"
fi
cp "$AGENT/SOUL.md" "$HH/SOUL.md"

echo "==> Skills Tequendama -> $HH/skills/seguria-*"
for d in "$AGENT"/skills/*/; do
  name="seguria-$(basename "$d")"
  ln -sfn "$d" "$HH/skills/$name"
  echo "   $name"
done

echo "==> Proveedor DeepSeek (config.yaml)"
if grep -q '^DEEPSEEK_API_KEY=..' "$HH/.env" 2>/dev/null; then
  hermes config set model.provider deepseek || true
  hermes config set model.default "${DEEPSEEK_MODEL:-deepseek-v4-flash}" || true
  echo "   provider=deepseek, default=${DEEPSEEK_MODEL:-deepseek-v4-flash}"
else
  echo "   (sin DEEPSEEK_API_KEY en $HH/.env — añádela y re-ejecuta, o configúrala a mano)"
fi

cat <<EOF

Listo. Para arrancar el agente:
  cd $AGENT && hermes
  # o headless:  hermes -z "Soy de Colombia, 34 años, quiero proteger a mi familia"

WhatsApp:  echo "WHATSAPP_ENABLED=true" >> $HH/.env && hermes gateway install && hermes whatsapp
API:       arranca la API (bash scripts/setup.sh api) en :8085 antes de conversar.
EOF
