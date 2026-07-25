#!/usr/bin/env bash
# Descarga los modelos ONNX de verificación biométrica (OpenCV Zoo) usados por
# apps/ai/app/identity.py: YuNet (detección, ~230 KB) + SFace (reconocimiento, ~37 MB).
#
# Se usa en el build de la imagen del servicio IA (deploy) y para desarrollo local.
# Si no hay red, no falla: identity.py también los descarga en runtime al primer uso.
set -euo pipefail

DEST="${1:-apps/ai/app/models/face}"
BASE="${SEGURIA_FACE_MODEL_BASE_URL:-https://github.com/opencv/opencv_zoo/raw/main/models}"
YUNET="face_detection_yunet_2023mar.onnx"
SFACE="face_recognition_sface_2021dec.onnx"

mkdir -p "$DEST"

fetch() {  # <subdir> <file>
  local url="$BASE/$1/$2" out="$DEST/$2"
  if [ -s "$out" ]; then echo "ya existe: $2"; return 0; fi
  echo "descargando $2 ..."
  curl -fsSL "$url" -o "$out"
  echo "  -> $out ($(du -h "$out" | cut -f1))"
}

fetch face_detection_yunet "$YUNET"
fetch face_recognition_sface "$SFACE"
echo "modelos faciales listos en $DEST"
