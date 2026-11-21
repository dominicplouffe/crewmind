# Spec changelog

Newest first. One line per change, citing the ids touched.

## Revision 2 (21 Nov 2026)

- **Renamed** the project from yaaf to crewmind: product, package, CLI, environment variables, Slack and mail prefixes (ADR-0008).
- **Full rewrite from revision 1:** chat-first front door (CHAT); token-only budgets with the budget as the wall and a CEO reserve (GOV-2, GOV-3, GOV-10); speed requirements (SPD); one quality dial (LLM-3); mailbox per project, managed (Stalwart) or manual, with per-agent accounts (INT-6, INT-10); Mem0 recall memory with an exact pinned layer (MEM); every file an artifact (ART); grilling (FND-15, FND-16); Agent Skills (LIB-6); agent browser (EXE-17); A2A (INT-11); OpenTelemetry export (NFR-22); slim mode on SQLite (NFR-23); Python stack (NFR-24); state machines (section 7); settings registry (Appendix A).
- **Owner decisions recorded:** Python; Postgres and SQLite; budgets count non-cached tokens only; Mem0; separate mailbox accounts per agent; subscription logins are the user's choice. See `docs/decisions/`.
- **Removed:** tempo and bar presets, stakes, dollar model budgets, run-count allowances and inbox lanes, the global plan gate, measurement windows, the change stamp, directives inferred from chat, the budget overage multiple.
