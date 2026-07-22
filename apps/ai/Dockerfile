FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
ENV SEGURIA_DB=/app/state/seguria.db SEGURIA_DOCS_DIR=/app/state/generated_docs
RUN mkdir -p /app/state
EXPOSE 8085
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8085"]
