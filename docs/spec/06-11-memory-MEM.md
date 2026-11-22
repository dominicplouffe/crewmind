### 6.11 Memory (MEM)

crewmind does not invent a memory system. It combines two well-established patterns:

- **Pinned memory:** a small, exact layer that is always in context. This is the "core memory" idea from MemGPT, now Letta.
- **Recall memory:** a searched layer of extracted facts, built on an established open-source library.

Governance facts live in the pinned layer, because they must never be fuzzy or missed.

- **MEM-1 Pinned memory (exact).**
  - Stored as governed records in the project database, never summarised by a model:
    - the goal and active standing orders;
    - closed decisions;
    - corrections and lessons (from mistake reports);
    - each agent's charter;
    - each agent's own pinned notes.
  - Every run of every agent receives the pinned records that concern it, in full.
  - Sizes are estimated at 4 characters per token and capped so they always fit: `memory.pinned_project_tokens` \[6,000\] for project-wide records and `memory.pinned_agent_tokens` \[2,000\] per agent. An agent's write past a cap is refused, naming what to retire. A chairman's write (a pin, a decision, a correction) is never refused by a cap: it succeeds and opens a flag asking the chairman to retire something. Lowering a cap below current use is refused, with the arithmetic.
- **MEM-2 Recall memory on an established library.**
  - The default engine is Mem0 (open source, Apache-2.0), used as a library inside the server, not as a separately exposed service. On Postgres it stores into the same database with pgvector; on SQLite (slim mode, NFR-23) it uses Qdrant in embedded mode, which runs in the server process and stores to a folder in the data directory. Neither needs an extra service. Mem0 also keeps its change history in a SQLite file of its own in the data directory, on every install; the file is backed up with the install and purged on forget and on project delete. Mem0's telemetry is switched off (NFR-1). The library is loaded on first use, not at start (NFR-23). The model is read from disk and never fetched at run time: without it, memory operations are refused with the command that installs it, and runs go on with pinned memory alone. On Postgres the `vector` extension must be enabled by a database superuser; a backup leaves extensions out, and a restore keeps the ones the database has. Mem0 handles fact extraction, de-duplication and updating.
  - Retrieval is hybrid: keyword (BM25) plus vector similarity.
  - Embeddings default to an open-source ONNX model running locally, so memory works without a key and without PyTorch. The model is shipped inside the crewmind package and the Docker image, so memory works offline from the first start. It is added when the package is built and is not kept in the source repository.
  - The engine sits behind a narrow interface (add, search, update, forget, history). Graphiti (a temporal knowledge graph; needs Neo4j or FalkorDB) or Letta can be swapped in as plug-ins without touching the rest of the product.
  - Home-grown memory algorithms are out of scope; only glue code is written.
- **MEM-3 Scopes.**
  - Recall memory is kept per project, per team and per agent.
  - Optionally, a chairman scope holds the chairman's preferences across projects, such as "plain English" or "never include taxes". It is opt-in, visible and editable by the chairman.
  - Agents read only the scopes they belong to (P3): the project's, their team's, their own, and the chairman's preferences. In a chat run an agent may write only its own scope (INV-23).
  - The chairman scope holds only what its owner adds; nothing is extracted into it.
- **MEM-4 Automatic extraction.**
  - After every work run, and every `memory.chat_extract_every` \[10\] chat turns, the platform extracts durable facts from the run's messages, outputs and artifacts: findings, preferences, lessons and context.
  - Extraction uses the platform extractor model (LLM-14) on a fast class and is metered against the project budget. Until the Founder's platform settings exist, it runs on the fast class of the credential that pays the project. Extracted facts go to the project scope. A run that used a tool reaching outside the project (web search) produces memories marked untrusted. Nothing is extracted at the budget wall; the run stays due.
  - A newer fact that contradicts an older one supersedes it. Both are kept with their validity dates.
- **MEM-5 Retrieval.** Each context pack includes the top `memory.recall_k` \[8\] recall memories for the run's task and latest messages. Each has its source link and date, and is marked untrusted where it came from outside (P4).
- **MEM-6 Visible and editable.**
  - The Memory panel shows what each agent and scope knows, searchable and dated.
  - The chairman can edit, pin or forget any entry. Pinning moves an entry into pinned memory: a project entry becomes a standing order, and a team's or an agent's entry becomes a pinned note of that agent (a team's goes to its lead).
  - Forgetting deletes the entry from the store and the index. The event log records that it was forgotten, without its content.
- **MEM-7 Nothing lives only in a session.**
  - Plans, notes, decisions and drafts are written through the agent API as they are made. A crash or restart loses at most the current model turn.
  - Chat runs save working notes every `memory.chat_extract_every` turns.
  - The CEO's plan is stored state, never conversation state.
- **MEM-8 Measured, not assumed.**
  - Published memory benchmark scores vary widely between vendor and third-party runs, so crewmind measures its own. A memory eval suite runs in CI.
  - Pinned recall must be 100%: every standing order, decision and correction must be present in every relevant context pack. This is checked mechanically.
  - Recall-layer accuracy is scored on project-history questions with scripted scenarios, and a regression fails the build.

Sources: [Mem0](https://github.com/mem0ai/mem0) · [Mem0 self-hosting on Postgres with pgvector](https://mem0.ai/blog/self-host-mem0-docker) · [Graphiti](https://github.com/getzep/graphiti) · [Zep and Graphiti paper](https://arxiv.org/abs/2501.13956) · [Mem0, Letta and Zep compared, including benchmark spreads](https://www.digitalapplied.com/blog/open-source-agent-memory-mem0-letta-zep-compared)
