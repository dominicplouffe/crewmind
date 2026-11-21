### 6.11 Memory (MEM)

crewmind does not invent a memory system. It combines two well-established patterns:

- **Pinned memory:** a small, exact layer that is always in context. This is the "core memory" idea from MemGPT, now Letta.
- **Recall memory:** a searched layer of extracted facts, built on an established open-source library.

Governance facts live in the pinned layer, because they must never be fuzzy or missed.

- **MEM-1 Pinned memory (exact).**
  - Stored as governed records in Postgres, never summarised by a model:
    - the goal and active standing orders;
    - closed decisions;
    - corrections and lessons (from mistake reports);
    - each agent's charter;
    - each agent's own pinned notes.
  - Every run of every agent receives the pinned records that concern it, in full.
  - Sizes are capped so they always fit: `memory.pinned_project_tokens` \[6,000\] for project-wide records and `memory.pinned_agent_tokens` \[2,000\] per agent. A write past a cap is refused, naming what to retire.
- **MEM-2 Recall memory on an established library.**
  - The default engine is Mem0 (open source, Apache-2.0), used as a library inside the server, not as a separately exposed service. On Postgres it stores into the same database with pgvector; on SQLite (slim mode, NFR-23) it uses an embedded, file-based vector store that Mem0 supports. Neither needs an extra service. Mem0 handles fact extraction, de-duplication and updating.
  - Retrieval is hybrid: keyword (BM25) plus vector similarity.
  - Embeddings default to a bundled open-source model running locally, so memory works without a key.
  - The engine sits behind a narrow interface (add, search, update, forget, history). Graphiti (a temporal knowledge graph; needs Neo4j or FalkorDB) or Letta can be swapped in as plug-ins without touching the rest of the product.
  - Home-grown memory algorithms are out of scope; only glue code is written.
- **MEM-3 Scopes.**
  - Recall memory is kept per project, per team and per agent.
  - Optionally, a chairman scope holds the chairman's preferences across projects, such as "plain English" or "never include taxes". It is opt-in, visible and editable by the chairman.
  - Agents read only the scopes they belong to (P3).
- **MEM-4 Automatic extraction.**
  - After every work run, and every `memory.chat_extract_every` \[10\] chat turns, the platform extracts durable facts from the run's messages, outputs and artifacts: findings, preferences, lessons and context.
  - Extraction uses the platform extractor model (LLM-14) on a fast class and is metered against the project budget.
  - A newer fact that contradicts an older one supersedes it. Both are kept with their validity dates.
- **MEM-5 Retrieval.** Each context pack includes the top `memory.recall_k` \[8\] recall memories for the run's task and latest messages. Each has its source link and date, and is marked untrusted where it came from outside (P4).
- **MEM-6 Visible and editable.**
  - The Memory panel shows what each agent and scope knows, searchable and dated.
  - The chairman can edit, pin or forget any entry.
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
