# ADR-0003: Budgets count non-cached tokens only

- **Status:** Accepted (21 Nov 2026, owner: Dominic)
- **Spec:** GOV-2, LLM-9, GOV-8

## Context

The owner wants token budgets only, and cache reads dominate long agent runs while costing far less.

## Decision

The budget counts input not served from a cache (cache writes included) plus output. Cache reads are recorded and shown, never counted. Real-world purchases are the only money budget.

## Consequences

The gateway must normalise each provider's cache usage fields; this is a phase 2 risk with recorded-response tests.
