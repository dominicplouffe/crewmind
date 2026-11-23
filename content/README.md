# v1 content

Imported on 22 Nov 2026 from `dominicplouffe/yaaf` at commit `b43bb78` (Apache-2.0): 38 roles, 17 crews, 12 example project specs, the design doctrine, the goal grammar and one Founder brief. The roles and crews are converted to the revision 2 formats, with three roles added (generalist, reviewer, gap-reviewer); what the conversion changed and left open is in `docs/spec-questions.md` (Q-012 to Q-015). The server ships a copy in `src/crewmind/content/library/`: run `scripts/sync_content.py` after editing.

The spec (section 12) keeps v1's content, not its code. What each folder holds:

| Folder | From v1 | Used by |
| --- | --- | --- |
| `roles/` | The role library (one file per role) | LIB-1, LIB-3 |
| `crews/` | Ready-made crews | LIB-2 |
| `examples/` | Example project specs | LIB-4, acceptance |
| `doctrine/` | The Founder's design doctrine | FND, LIB-6 |
| `goal-grammar/` | The ten-element goal grammar and its examples | FND-7 |
| `mcp-servers/` | Not from v1: well-known MCP servers, checked 23 Nov 2026, that fill in the add form | CON-15 |

Roles follow LIB-1: no model names or effort levels. They may set `min_class` and a vision requirement instead.
