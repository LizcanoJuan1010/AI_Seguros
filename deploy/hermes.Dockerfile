# Imagen del agente SegurIA sobre Hermes Agent (NousResearch).
# Incluye OfficeCLI para presentaciones/documentos y las herramientas que Hermes usa
# (node, ffmpeg, ripgrep, git). El workspace (SOUL.md, AGENTS.md, skills) se monta.
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    HERMES_HOME=/root/.hermes \
    HERMES_NONINTERACTIVE=1 \
    PATH="/root/.local/bin:${PATH}"

# Dependencias que Hermes espera en runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates git ripgrep ffmpeg nodejs npm bash \
    && rm -rf /var/lib/apt/lists/*

# uv (gestor de venv que usa Hermes)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Hermes Agent (instalación oficial no interactiva)
RUN curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash \
    || (echo "fallback: instala Hermes desde git" && \
        git clone --depth 1 https://github.com/NousResearch/hermes-agent \
            /root/.hermes/hermes-agent && \
        cd /root/.hermes/hermes-agent && \
        /root/.local/bin/uv venv venv && \
        /root/.local/bin/uv pip install --python venv/bin/python -e .)

# OfficeCLI (presentaciones/documentos)
RUN curl -fsSL https://raw.githubusercontent.com/iOfficeAI/OfficeCLI/main/install.sh | bash

COPY deploy/hermes-entrypoint.sh /usr/local/bin/hermes-entrypoint.sh
RUN chmod +x /usr/local/bin/hermes-entrypoint.sh

WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/hermes-entrypoint.sh"]
