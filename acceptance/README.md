# Acceptance references

The acceptance suite (spec section 13) runs against fixed reference material kept here. Write each item in the phase that first needs it, and keep it stable afterwards: changing a reference changes what "passing" means.

| File to create | Needed by | Contents |
| --- | --- | --- |
| `deliver.spec.json` | Phase 2, golden path | A small Deliver project spec (LIB-4) whose longest dependency chain is known, so the speed criterion can be computed |
| `explore.spec.json` | Phase 5 | An Explore spec with two bets: one the scripted crew confirms, one it kills |
| `operate.spec.json` | Phase 5 | A weekly Operate spec with one recurring requirement |
| `scripts/` | Phase 2 onward | Scripted-crew scripts for the mock harness: competent crew, rule-breaker (INV-1 to INV-7 and INV-23), quiet losing CEO, frustration scenarios (NFR-19) |
| `raw-brief.md` + `raw-brief.grades.json` | Phase 7 | A one-paragraph brief that must grade "not ready", with its hand grade |
| `reference-goal.md` + `reference-goal.grades.json` | Phase 7 | A goal that grades "ready", with the hand-graded result for each of the ten grammar elements |
| `grill-document.md` + `grill-document.expected.json` | Phase 7 | A long brief seeded with two contradictions, one illustrative number, one unverifiable requirement and one conflict with a standing order; the expected questions |
| `test-site/` | Phase 8 | A local website with a login and a payment form for the browser tests |
| `a2a-test-agent/` | Phase 8 | A minimal A2A agent for the interoperability tests |

Each scenario's expected outcome is written down before the code that makes it pass.
