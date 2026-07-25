FROM python:3.12-slim
WORKDIR /app
# libglib2.0 + curl los requiere opencv-python-headless / la descarga de modelos
# (verificación biométrica YuNet + SFace).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Modelos ONNX de biometría (OpenCV Zoo) horneados en la imagen para no depender de
# red en runtime. Si el build está offline, identity.py los descarga al primer uso.
ENV SEGURIA_FACE_MODEL_DIR=/app/app/models/face
RUN mkdir -p "$SEGURIA_FACE_MODEL_DIR" && \
    for m in "face_detection_yunet/face_detection_yunet_2023mar.onnx" \
             "face_recognition_sface/face_recognition_sface_2021dec.onnx"; do \
        curl -fsSL "https://github.com/opencv/opencv_zoo/raw/main/models/$m" \
             -o "$SEGURIA_FACE_MODEL_DIR/$(basename "$m")" || \
        echo "aviso: no se pudo hornear $(basename "$m"); se descargará en runtime"; \
    done
COPY app ./app
# El servicio IA usa PostgreSQL EXCLUSIVAMENTE (cero SQLite). La conexión sale de
# DATABASE_URL (la inyecta docker-compose; en Docker el host es `postgres`), y todas
# las tablas viven en el esquema `seguria`. Aquí solo queda el dir de PDFs generados.
ENV SEGURIA_DOCS_DIR=/app/state/generated_docs
RUN mkdir -p /app/state
EXPOSE 8085
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8085"]
