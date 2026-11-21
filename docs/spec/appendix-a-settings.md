## Appendix A. Settings registry

Every governed number and switch, with its default and allowed range. Scopes:

- **project:** a per-project governed setting, changed by the chairman with a reason (GOV-1).
- **person:** a per-person preference.
- **install:** set by the admin.

Values marked "starting default" have no v1 history behind them and are expected to be tuned from measured use. Projects record which registry version their defaults came from.

| Setting | Default | Range | Scope | Used by |
| --- | --- | --- | --- | --- |
| `quality` | balanced | fast, balanced, best | project | LLM-3 |
| `budget.tokens` | Deliver 20M total; Explore 10M total; Operate 40M per month, all non-cached tokens (starting defaults; the Founder sizes each project) | 1M or more | project | GOV-2 |
| `budget.ceo_reserve` | 10% of the budget | 0 (off)–50% | project | GOV-3, GOV-10 |
| `budget.warn_at` | 80% | 50–95% | project | GOV-3 |
| `budget.wrapup_at` | 90% | 60–99% | project | GOV-3, PLN-3 |
| `run.max_tokens` | 3M | 0 (off) or 100k–50M | project | GOV-6 |
| `run.timeout` | 90 min | 10–360 min | project | EXE-7, WRK-4, WRK-7 |
| `run.concurrency` | 4 | 1–16 | project | SPD-1, GOV-7, EXE-3 |
| `agent.max_wakes_per_hour` | 12 | 1–60 | project | GOV-7, EXE-3 |
| `spin.window` | 6 runs | 3–20 | project | GOV-7 |
| `refusal.cap` | 5 | 3–20 | project | EXE-10 |
| `heartbeat.every` | 6 h | 1–24 h | project | EXE-2 |
| `stall.after` | 60 min | 15 min–12 h | project | EXE-16 |
| `start.first_task_within` | 10 min | 5–120 min | project | SPD-3 |
| `output.first_within` | 6 h | 1–72 h | project | SPD-4 |
| `seat.idle_after` | 3 days | 1–14 days | project | SPD-9 |
| `explore.timebox` | 7 days | 1–90 days | project | PRJ-7, SPD-7 |
| `bet.window` | 48 h | 4 h–14 days | project | PRJ-7, SPD-7 |
| `completion.auto_after` | 24 h | 0 (off)–7 days | project | PRJ-4, HUM-2 |
| `reopen.window` | 14 days | 0–90 days | project | PRJ-6 |
| `delete.grace` | 7 days | 1–30 days | install | PRJ-10 |
| `tasks.max_open` | 8 | 1–30 | project | WRK-3 |
| `tasks.max_subtasks` | 10 | 1–30 | project | WRK-3 |
| `teams.max` | 8 | 1–20 | project | EXE-1 |
| `evidence.min_share` | 50% (Explore only) | 0–100% | project | WRK-3 |
| `evidence.drought_after` | 24 h (Explore only) | 6 h–14 days | project | WRK-3 |
| `review.independent` | on | on; off only when solo | project | WRK-9 |
| `audit.sample_rate` | 20% | 0–100% | project | WRK-13 |
| `audit.window` | 48 h | 12 h–14 days | project | WRK-13, HUM-2 |
| `watch.min_interval` | 15 min | 5 min–24 h | install | WRK-17 |
| `approval.window` | 7 days | 1–30 days | project | HUM-2 |
| `question.window` | 24 h | 1–72 h | project | HUM-2, HUM-5 |
| `question.max_open` | 3 | 1–10 | project | HUM-5 |
| `decision.reopen_cooldown` | 7 days | 1–90 days | project | MSG-5 |
| `correction.ttl` | 30 days | 1 day–forever | project | MSG-6 |
| `listening.flag_at` | 3 corrections in 7 days | 1–20 | project | HUM-6 |
| `thread.freeze_after` | 10 messages | 4–50 | project | MSG-9, INT-10 |
| `report.cadence` | off | off, or 1–4 slots a day | project | MSG-8 |
| `chat.keep_warm` | 10 min | 1–60 min | install | MSG-11 |
| `chat.brevity` | normal | short, normal, detailed | person | CHAT-13, MSG-12 |
| `brief.time` | 08:00 local | any time; or off | person | HUM-11 |
| `brief.away_after` | 4 h | 1–48 h | person | CHAT-15 |
| `review.every` | 7 days | 1–30 days | project | HUM-9 |
| `agenda.days` | 14 | 1–90 | person | HUM-12 |
| `metric.read_every` | 24 h | 1 h–30 days | project | PLN-11 |
| `memory.pinned_project_tokens` | 6,000 | 2,000–20,000 | project | MEM-1 |
| `memory.pinned_agent_tokens` | 2,000 | 500–8,000 | project | MEM-1 |
| `memory.recall_k` | 8 | 0–32 | project | MEM-5 |
| `memory.chat_extract_every` | 10 turns | 3–50 | install | MEM-4, MEM-7 |
| `upload.max_size` | 100 MB | 1 MB–2 GB | install | CHAT-9 |
| `artifact.max_size` | 100 MB | 1 MB–2 GB | install | ART-6 |
| `storage.quota` | 20 GB | 1 GB or more | project | ART-6 |
| `retention.traces` | 90 days | 7 days–forever | install | NFR-15 |
| `retention.snapshots` | 30 days | 1 day–forever | install | NFR-15 |
| `alerts.level` | decisions and alarms | everything; decisions and alarms; alarms only | person | INT-7 |
| `alerts.grace` | 60 min | 0–24 h | person | INT-7 |
| `alerts.max_per_day` | 5 | 1–50 | person | INT-7 |
| `email.mode` | off | off, managed, manual, install alias | project | INT-6 |
| `email.max_per_day` | 30 | 1–500 | project | INT-6 |
| `search.max_per_day` | 200 | 0–5,000 | project | INT-8 |
| `spend.enabled` | off | on, off | project | GOV-8 |
| `spend.currency` | USD | ISO 4217 code | project | GOV-8 |
| `spend.monthly_cap` | 500 | 0 or more | project | GOV-8 |
| `spend.approval_at` | 100 | 0 or more | project | GOV-8 |
| `email.max_new_threads_per_day` | 20 | 1–200 | project | INT-6 |
| `email.thread_freeze_after` | 40 messages | 10–500 | project | INT-6 |
| `email.agent_addresses` | off | on, off | project | INT-10 |
| `budget.reserve_min_done` | 75% of accepted requirements met (Deliver) | 50–100% | project | GOV-10 |
| `grill.pace` | one at a time | one at a time, batch | person | FND-4, FND-15, FND-16 |
| `browser.keep_sessions` | on | on, off | project | EXE-17 |
| `a2a.enabled` | off | on, off | project | INT-11 |
| `otel.endpoint` | none (export off) | an OTLP URL | install | NFR-22 |
| `otel.capture_content` | off | on, off | project | NFR-22 |
