## 10. Background processes

There are two long-running programs plus disposable sandboxes:

- The **server** holds every rule, runs the scheduled jobs and hosts the model gateway.
- **Runners** (one or more) lease runs and execute them. Without a runner, nothing executes; the server never runs an agent itself.

The background rules:

- **BG-1** Each project is processed in its own transaction on every tick, so one broken project cannot stall the others.
- **BG-2** Database notifications SHOULD be used to cut wake latency to near zero. Polling is the safety net, and nothing depends on a notification arriving. Within one server process, every write operation and every job pass that changed something wakes the waiting jobs at once, at most once every 200 ms; the intervals below are the longest a job waits.
- **BG-3** Every scheduled job is idempotent and safe to run twice.

| Job | Interval | Does |
| --- | --- | --- |
| Dispatcher | 2 s, plus on notification | Derives wake triggers (EXE-2), applies limits (EXE-3), queues runs |
| Scheduler | 15 s per project | In order: apply due settings changes and resume times; reap dead runs; expire bets, decision items and claims; enforce budget thresholds; requeue lost checks (alert the CEO after 3); elect leads; automatic stand-downs; commitments, reviews and cycle rolls; flags (slow start, no visible output, seat idle, spinning, stall, drought); memory caps |
| Brief builder | At each person's `brief.time`; on return after `brief.away_after` | Daily brief and since-you-were-away summaries at 0 tokens |
| Verifier | Continuous | Verifies pending outside evidence (WRK-12) |
| Watch runner | Per watch interval | Runs launch watches at 0 tokens (WRK-17) |
| Metric reader | `metric.read_every` | Reads metric requirements from outside sources |
| Memory extractor | After each work run; every `memory.chat_extract_every` chat turns | Extracts and updates recall memory (MEM-4) |
| Runner supervisor | 5 s | Leases runs, starts sandboxes, sends heartbeats, keeps warm chat sessions within `chat.keep_warm` |
| Check runner | On demand | Runs command tests in throwaway sandboxes (WRK-7) and red-first checks at task creation (WRK-5) |
| Model gateway | Always on | Routes and meters every model call; enforces per-run caps (LLM-9) |
| Upkeep | Daily | Refreshes lineups and each credential's model list; flags seats on retired models; purges expired data (NFR-15) |
| Slack and mail bridges | Event-driven; IMAP IDLE, or polling every minute | Mirrors the project chat and project mail (INT-5, INT-6) |
| Notifier | On event | Applies grace periods and caps, then sends alerts (INT-7) |
| Mail provisioner | On demand | Creates, disables, enables and deletes managed project and agent mailboxes through the mail-server adapter; checks DNS (INT-6, INT-10) |
| Telemetry exporter | Continuous, when configured | Sends OpenTelemetry traces and metrics to the admin's collector (NFR-22) |

- **BG-4** Every automatic state change a job makes writes an event naming the job as actor. Anything that "decided itself" appears in the next daily brief and the since-you-were-away summary.
