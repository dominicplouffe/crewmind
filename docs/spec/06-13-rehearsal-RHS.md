### 6.13 Rehearsal: the zero-token fire drill (RHS)

- **RHS-1 Safe by construction.** Rehearsing a spec runs the real rule engine, dispatcher and scheduler against the mock harness with a scripted, competent crew. It spends 0 tokens, never contacts the network, never runs commands from the spec, never reads credentials, never notifies anyone, and always runs on a fresh in-memory SQLite database of its own: the code refuses any other.
- **RHS-2 Clock rules.** Only wall-clock rules (heartbeats, windows, watch intervals) are compressed. The report states their real effect from the actual numbers. Every other rule is in force.
- **RHS-3 Report contents:**
  - a verdict;
  - the walk, each step with when it happened: roles resolve, teams hire, CEO plans, scope accepted, work claimed, first deliverable, closes with evidence;
  - every time the drill waited for the chairman, by kind;
  - staffing findings, such as a review asked for with nobody hired who can give it;
  - rules hit, with counts;
  - estimated runs and tokens, from install history when there is enough;
  - the projected duration, the longest dependency chain and how much parallelism the roster allows;
  - setup still missing, and what the drill could not exercise;
  - a statement that the drill does not predict quality.
- **RHS-4 Surfaces.** Available from the chat, API, CLI, MCP and the Founder. Output is text or JSON.
