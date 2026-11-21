# ADR-0004: Mem0 for recall memory; exact pinned memory in our own tables

- **Status:** Accepted (21 Nov 2026, owner: Dominic)
- **Spec:** MEM-1 to MEM-8

## Context

The owner asked for known science, not a home-grown memory system.

## Decision

Mem0 (Apache-2.0) as an in-process library behind a narrow interface, on pgvector or an embedded store. Standing orders, decisions, corrections and lessons are exact governed records, never fuzzy memory. Graphiti or Letta can be plugged in later.

## Consequences

Recall quality is measured by our own eval suite (MEM-8), not vendor benchmarks.
