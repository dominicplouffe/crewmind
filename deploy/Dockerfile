# The crewmind server image, for the full-server shape (NFR-2).
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web ./
RUN npm run build

FROM python:3.13-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --locked --no-dev
# The local embedding model ships inside the image, so memory works offline (MEM-2).
RUN .venv/bin/python -m crewmind.domain.memory.fetch_model
COPY --from=web /web/dist ./src/crewmind/web_dist

ENV PATH="/app/.venv/bin:$PATH" \
    CREWMIND_DATA_DIR=/data
VOLUME /data
EXPOSE 8420

# Inside the container the server listens on every interface; the Compose file publishes
# the port on the host's 127.0.0.1 only, which keeps the NFR-6 default.
CMD ["crewmind", "up"]
