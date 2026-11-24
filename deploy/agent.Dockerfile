# The Nightsquad agent image: what every agent run and every platform check executes in,
# in container mode (EXE-12, WRK-7).
#
#   docker build -f deploy/agent.Dockerfile -t nightsquad-agent .
#
# It holds the harness loop and common tools, and nothing of the server: no database
# driver, no key, no server code. The harness needs only an HTTP client (P3, LLM-8).
FROM node:22-slim AS node

FROM python:3.13-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git jq \
    && rm -rf /var/lib/apt/lists/*

# Node and npm, for projects that build for the web.
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

RUN pip install --no-cache-dir --disable-pip-version-check "httpx>=0.27"

# The harness goes into site-packages because it is started with `python -I`, which
# ignores PYTHONPATH.
COPY src/nightsquad/__init__.py /usr/local/lib/python3.13/site-packages/nightsquad/__init__.py
COPY src/nightsquad/runner/__init__.py src/nightsquad/runner/agent.py \
    /usr/local/lib/python3.13/site-packages/nightsquad/runner/

# The server names the user at start (EXE-12); this one is the default.
RUN useradd --create-home --uid 10001 agent
USER agent
WORKDIR /workspace
