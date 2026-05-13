# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for git integration + healthchecks
RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY config ./config

RUN pip install --upgrade pip \
 && pip install .

# Default writable state + projects volumes
RUN mkdir -p /data/state /data/projects
ENV LLD_STATE_DIR=/data/state \
    LLD_PROJECTS_DIR=/data/projects

EXPOSE 8765

# Note: the container talks to Ollama on the host via host.docker.internal
# (Linux: --add-host=host.docker.internal:host-gateway).
ENTRYPOINT ["local-llm-dev"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8765"]
