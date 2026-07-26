FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
# El servicio IA usa PostgreSQL EXCLUSIVAMENTE (cero SQLite). La conexión sale de
# DATABASE_URL (la inyecta docker-compose; en Docker el host es `postgres`), y todas
# las tablas viven en el esquema `seguria`. Aquí solo queda el dir de PDFs generados.
ENV SEGURIA_DOCS_DIR=/app/state/generated_docs
RUN mkdir -p /app/state
EXPOSE 8085
# $PORT: Railway (y otros PaaS) inyectan su propio puerto dinámico; docker-compose
# no fija PORT así que cae al 8085 de siempre (sin cambio de comportamiento local).
# Forma shell (no exec) a propósito: es la única que expande variables de entorno.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8085}
