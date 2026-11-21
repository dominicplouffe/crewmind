## 1. Purpose, users and the experience bar

crewmind runs a team of AI agents like a company, unattended, for hours to weeks, under rules the agents cannot talk their way out of. A person states a goal in a chat; the platform staffs a CEO agent and specialists, gives them a token budget, and keeps them working fast while the person stays in charge as **chairman**.

### 1.1 The problem and the thesis

**The problem.** A single agent is fine for a task you watch. Long-running autonomous work fails in predictable ways. Agents declare their own work done, spend without limit, loop talking to each other and move the goalposts. They forget what they were told, flatter whoever is watching, go quiet, and either wait to be told or run ahead of what was asked. Prompting against these failures does not work, because a prompt is a request the model may ignore.

**The thesis.** Every rule that matters is enforced by the server as a refusal or an automatic state change, at a point the agent's credentials cannot reach around. Everything that cannot be a rule (tone, judgement, quality) is measured, shown and fed back, never left to hope.

### 1.2 Who it is for

- **The chairman:** anyone who wants a goal pursued without supervising it hour by hour, from a one-day build to a standing weekly operation. Technical skill helps but is not required. The chairman never needs to know model names, effort levels, harnesses or run limits.
- **Self-hosted only:** one server or one desktop, open source, no vendor account, no telemetry. The chairman pays model providers with their own keys or subscriptions.
- **Not for quick, watched tasks.** A single agent is cheaper there, and the product says so.

### 1.3 The experience bar

These targets are product requirements. Each is measured in the acceptance suite (section 13) or by the platform at runtime.

| Moment | Target |
| --- | --- |
| Install to first running project | 10 minutes or less on a prepared server |
| Goal described to project running | 5 minutes or less through the Founder; 2 minutes in quick mode |
| Chairman message shown as delivered | 1 second or less |
| Agent reply, or a platform status saying why not | 60 seconds or less, always; first words within 5 seconds on a warm chat |
| Deliver: first task claimed | 10 minutes or less after start |
| Deliver: first usable output | Early; flagged when none exists after `output.first_within` \[6 h\] of running |
| Idle project | 0 tokens |
| Spend past the budget | Only the CEO reserve the chairman allowed, drawn to finish nearly-done work; nothing beyond runs already in flight at the wall |
| Choices needed to start | Goal, who pays, budget. Everything else has a default |

### 1.4 Outcomes a working rebuild produces

- The chairman describes a goal in their own words and gets a running, staffed project in minutes.
- Work starts at once and runs in parallel; Deliver produces something usable early and finishes as soon as the work allows.
- "Done" means verified by something other than the agent that did the work.
- Spending is metered in tokens per run and stops at the budget the chairman set, with a small CEO reserve for finishing.
- The chairman says a thing once. Standing orders, decisions and corrections persist exactly.
- The chairman is interrupted only for decisions that are genuinely theirs, never left in silence, and can always see what is happening now, next, and what waits on them.
- Every message, run, token and decision is kept and can be audited.
- The chairman can run everything from the project chat, the command line, Slack or an AI assistant (via MCP), with equal capability.

### 1.5 What users told us, and what the rebuild promises

The table compiles the complaints raised across v1 projects (counts are approximate) and the mechanism that answers each one.

| Frustration (count) | What happened | Rebuild promise | Enforced by |
| --- | --- | --- | --- |
| 1. It doesn't listen (\~60) | Forgot standing orders, read examples as data, invented rules, re-argued closed decisions, answered a different question | Say it once. Pins, decisions, corrections and examples are exact records in every run | P16; MSG-4 to MSG-7; MEM-1; CHAT-11, CHAT-12 |
| 2. Shallow, wrong or unchecked work (\~75) | Fabricated prices, miscounted figures, "done" when not, low ambition, the chairman finding gaps | Figures carry a basis; tests fail before they pass; independent review; a final gap review against a named standard | WRK-5, WRK-9, WRK-10, WRK-11; FND-7 |
| 3. Too long, cryptic, jargon (\~50) | Walls of probabilities, unclear asks | Plain words: the answer or the ask first, a "Need from you" line, length budgets | P18; MSG-12; HUM-1 |
| 4. Silent, idle, late (\~60) | No reply, missed report times, launches left unwatched | Never silent; reports built by the platform on time; launches carry watches | P17; CHAT-3; HUM-11; WRK-17; EXE-16 |
| 5. Wrong initiative, both ways (\~45) | Asked permission for delegated calls; acted on chat; kept running after "stand down" | Autonomous by default; asking about a held decision is refused; chat is not command; holds are mechanical | P15; HUM-4; MSG-3; PRJ-2 |
| 6. Money on busywork (\~30) | Agents polling for tasks, idle crews, asking for budget while it sat unused | 0 tokens when idle; no polling; idle seats flagged; raise requests refused while the budget is under-used | P8; EXE-2; HUM-6; GOV-5 |
| 7. Can't see what's going on (\~20) | Lost track, too many documents, no visible tasks | Now / Next / Waiting-on-you header; one deliverables list; every run tied to the requirement it serves | CHAT-18; ART-3; EXE-4 |
| 8. Flattery instead of fixes (few, sharp) | "You're right" without action; spending then apologising | Disagree with reasons; mistakes carry their cost and fix | MSG-12; HUM-8; NFR-19 |
| 9. The platform itself | Silent limits killed 1,224 runs; a crash lost a plan; approvals missed the desk; broken notice titles; credentials missing in chat | Every hold visible with its lift time; plans saved as made; one decision-item type on every surface; typed titles; one credential resolver | EXE-4; MEM-7; HUM-1; IF-1.3; LLM-7 |
