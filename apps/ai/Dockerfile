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
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8085"]
