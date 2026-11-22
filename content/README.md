# v1 content

Imported on 22 Nov 2026 from `dominicplouffe/yaaf` at commit `b43bb78` (Apache-2.0), unchanged: 38 roles, 17 crews, 12 example project specs, the design doctrine, the goal grammar and one Founder brief. The files are still in v1's format. Phase 7 converts them: roles lose `effort` and gain the revision 2 fields, and names that say "yaaf" become crewmind.

The spec (section 12) keeps v1's content, not its code. What each folder holds:

| Folder | From v1 | Used by |
| --- | --- | --- |
| `roles/` | The role library (one file per role) | LIB-1, LIB-3 |
| `crews/` | Ready-made crews | LIB-2 |
| `examples/` | Example project specs | LIB-4, acceptance |
| `doctrine/` | The Founder's design doctrine | FND, LIB-6 |
| `goal-grammar/` | The ten-element goal grammar and its examples | FND-7 |

Imported roles must be converted to the revision 2 role fields (LIB-1): no model names or effort levels. They may set `min_class` and a vision requirement instead. Note conversion problems in `docs/spec-questions.md`.
