# Spec questions

Questions raised while building, for the owner. Coding agents add entries here instead of guessing (see CLAUDE.md). Close an entry by recording the answer and the spec change it caused.

| Id | Raised | Spec ref | Quote | Question | Recommendation | Status | Answer |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Q-001 | 2026-11-21 | MEM-2, NFR-23 | "an embedded, file-based vector store that Mem0 supports" | Which embedded vector store does Mem0 support that runs well beside SQLite in one process? | Choose during phase 3 from Mem0's supported stores; prefer one with no server process | open | |
| Q-002 | 2026-11-21 | INT-6 | "tested in CI against a pinned Stalwart version" | Which Stalwart version to pin? | The latest stable release at the start of phase 8 | open | |
| Q-003 | 2026-11-21 | INT-11 | "version 1.x, pinned in CI" | Which A2A SDK and version? | The official A2A Python SDK, latest 1.x at the start of phase 8 | open | |
| Q-004 | 2026-11-21 | LLM-12, Appendix A | "An install-wide concurrency ceiling per provider" | Appendix A has no setting for the ceiling. The build stores one number per provider, set by an admin with `models set-ceiling` and recorded in the event log; a provider with no ceiling is not limited. Should there also be a default ceiling as a registry setting? | Keep the per-provider value and add no default: a wrong default would throttle installs with high rate limits. State this in LLM-12 | open | |
| Q-005 | 2026-11-21 | GOV-7, EXE-16 | "consecutive work runs in a project change no work state" / "open work or open scope" | Spinning and the stall watchdog are listed in phase 2 but both depend on tasks and scope, which arrive in phases 3 and 4. May they move to phase 4? | Move GOV-7 (spinning part) and EXE-16 to phase 4. The other runaway guards (concurrency, wake limit, pair breaker, refusal cap) are built | open | |
| Q-006 | 2026-11-21 | Claude API key for live tests | n/a | The cloud build environment cannot hold an Anthropic key as a protected network secret, only as a plain environment variable that every session and command in the environment can read. How should the real-provider exit demo be run? | Run it on the owner's machine with the steps in the README, or add `ANTHROPIC_API_KEY` to the `crewmind` cloud environment knowing it is readable there | open | |
