# ADR-0010: The egress proxy is built in-house

- **Status:** Accepted (23 Nov 2026, owner decision on the phase 7.B plan)
- **Spec:** CON-6, EXE-14, NFR-24

## Context

A secret sent for the agent (CON-6) is added to the agent's HTTPS requests by a proxy that every run's traffic passes through. The proxy runs beside the master key, so what it is built from matters more than for most components.

mitmproxy (MIT licence, version 12.3.1) is the established Python library for this. Installed into this project it brings 26 packages, among them Flask, Tornado, a terminal UI (urwid), an LDAP client and a QUIC stack. None of them is needed to add a header to an HTTP/1.1 request, and each widens what runs in the process holding the master key.

## Decision

The egress proxy is a small, single-purpose component written for Nightsquad on libraries already in the stack: asyncio for connections, `h11` for HTTP/1.1, `cryptography` for the certificate authority and leaf certificates, and the standard `ssl` module for TLS. It:

- relays every connection as an opaque tunnel, except connections to a site that has a secret sent for the connecting run;
- terminates TLS only for those sites, adds the header, verifies the real site's certificate, and relays the response;
- identifies the run from the proxy credential (its run token) and holds no state beyond a short-lived certificate cache.

## Consequences

- Fewer dependencies in the process that holds the master key, and code the project can read and test end to end.
- The project owns the edge cases mitmproxy has already solved: chunked bodies, keep-alive, upgrades, slow clients. Attack and contract tests cover each one before the proxy is called done (phase 7.B, part 7B.3).
- HTTP/2 to the agent is not offered; the proxy offers HTTP/1.1, which every client supports.
- If the proxy ever needs to understand much more of HTTP, this decision is revisited rather than the proxy grown.
