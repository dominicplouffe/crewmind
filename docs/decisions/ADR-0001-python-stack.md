# ADR-0001: Python for everything except the web app

- **Status:** Accepted (21 Nov 2026, owner: Dominic)
- **Spec:** NFR-24, IF-1.2

## Context

The owner prefers Python. The memory library (Mem0) and the model gateway library (LiteLLM) are Python projects, so they run inside the server rather than as extra services.

## Decision

Python 3.12+ for server, runners, gateway, memory, CLI and MCP server, with the libraries in NFR-24. The web app is TypeScript/React, because a streaming chat at the section 5 bar needs it; its API client is generated from OpenAPI and holds no business rules.

## Consequences

Deviation from a SHOULD library needs a new decision record.
