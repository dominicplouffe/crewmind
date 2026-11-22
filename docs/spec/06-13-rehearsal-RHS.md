### 6.13 Rehearsal: the zero-token fire drill (RHS)

- **RHS-1 Safe by construction.** Rehearsing a spec runs the real rule engine, dispatcher and scheduler against the mock harness with a scripted, competent crew. It spends 0 tokens, never contacts the network, never runs commands from the spec, never reads credentials, never notifies anyone, and always runs on a fresh SQLite database of its own, in a folder made for the drill and deleted after it: the code refuses a database that already exists. The drill is a process of its own that is given the spec and nothing else, and stops after `rehearsal.max_seconds` \[60 s\]. Its crew is code, not a model: each agent reads the plan and the board and takes the next step a competent agent in that seat would. It runs one agent at a time so that the same spec always gives the same report.
- **RHS-2 Clock rules.** Only wall-clock rules (heartbeats, windows, watch intervals) are compressed. The report states their real effect from the actual numbers. Every other rule is in force. The walk ends at the first verified close: a Deliver project is ready, an Explore bet has its finding, an Operate requirement is met.
- **RHS-3 Report contents:**
  - a verdict;
  - the walk, each step with when it happened: roles resolve, teams hire, CEO plans, scope accepted, work claimed, first deliverable, closes with evidence;
  - every time the drill waited for the chairman, by kind;
  - staffing findings, such as a review asked for with nobody hired who can give it;
  - rules hit, with counts;
  - estimated runs and tokens to the first close, from install history when there is enough (at least 10 finished runs); a rehearsal does not estimate the whole project;
  - the projected duration, the longest dependency chain and how much parallelism the roster allows;
  - setup still missing, and what the drill could not exercise;
  - a statement that the drill does not predict quality.
- **RHS-4 Surfaces.** Available from the chat, API, CLI, MCP and the Founder. Output is text or JSON.
