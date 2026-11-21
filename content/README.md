# v1 content to import

The spec (section 12) keeps v1's content, not its code. Copy these from v1 into this folder before phase 7:

| Folder | From v1 | Used by |
| --- | --- | --- |
| `roles/` | The role library (one file per role) | LIB-1, LIB-3 |
| `crews/` | Ready-made crews | LIB-2 |
| `examples/` | Example project specs | LIB-4, acceptance |
| `doctrine/` | The Founder's design doctrine | FND, LIB-6 |
| `goal-grammar/` | The ten-element goal grammar and its examples | FND-7 |

Imported roles must be converted to the revision 2 role fields (LIB-1): no model names or effort levels. They may set `min_class` and a vision requirement instead. Note conversion problems in `docs/spec-questions.md`.
