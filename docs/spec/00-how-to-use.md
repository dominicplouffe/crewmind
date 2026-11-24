## How to use this document

This is the complete brief for rebuilding Nightsquad in a new, empty repository. It says what the product must do and why, not how v1 did it.

- **Audience:** an implementing model or engineer with no access to the v1 code.
- **Deliberately absent:** v1 source, database schema, endpoint paths and screen layouts. Choose your own; v1's choices are part of what is being replaced. The technology stack is fixed in NFR-24.
- **Normative words:** MUST = required for a conforming rebuild; SHOULD = strong default, deviate only with a written reason; MAY = optional.
- **Requirement ids** (e.g. `GOV-3`) are stable from this revision on, so tests, commits and reviews can cite them. Revision 2 renumbered them; v1-era citations do not carry over.
- **Numbers:** every tunable number is a named setting listed in Appendix A, with its default, range and scope. Requirement text cites the setting name in backticks (e.g. `budget.ceo_reserve`) and its default in brackets. Appendix A is authoritative for values; a number written in a requirement without a setting name is a fixed rule.
- **Order of authority:** Principles (section 2) override everything. Invariants (section 8) override requirements. A conflict goes in Open questions (section 14), never into code.

**What changed in revision 2** (21 Nov 2026), driven by the owner's direction and a review of v1 projects:

- **Chat first.** A project is a conversation, at the standard of the best coding assistants. The chairman can talk to any agent. Uploads are supported, and every file is an artifact (sections 5 and 6.7).
- **Token budgets only.** The budget is the wall, except for a small reserve the CEO may draw to finish work that is nearly done, as a real CEO would. Real-world purchases are the only thing still counted in money (section 6.4).
- **Speed is a feature.** There are no clock-based waits on ready work. Deliver ships a first usable version early and finishes as fast as budget and concurrency allow (section 6.2).
- **One quality dial** replaces choosing models and effort levels per role (section 6.3).
- **Simpler integrations:** one Slack channel per project. A project can get its own email address, created on a connected mail server such as Stalwart or set up by hand, and its agents can email external agents (section 6.15).
- **Proven memory:** an established open-source memory library and a known two-layer design, not a home-grown one (section 6.11).
- **Every frustration from v1 projects maps to a mechanism** (section 1.5).
- **Open standards:** Agent Skills (LIB-6), an agent browser (EXE-17), the A2A protocol (INT-11) and OpenTelemetry export (NFR-22).
- **Stack and footprint:** Python (NFR-24). Postgres for a full server, or SQLite for a slim one-process install (NFR-23).
- **Removed:** tempo and bar presets, stakes, dollar model budgets, run-count allowances and inbox lanes, the global plan gate, measurement windows, the change stamp, and directives inferred from chat.
