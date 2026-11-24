# ADR-0006: Subscription logins are the user's decision

- **Status:** Accepted (21 Nov 2026, owner: Dominic)
- **Spec:** LLM-2, LLM-8, NFR-14

## Context

Some providers' consumer terms may restrict automated use. The owner's position: it is the user's usage and their decision.

## Decision

Nightsquad supports subscription logins without blocking or warning. SECURITY.md still states plainly where a subscription harness cannot use the model gateway.

## Consequences

None for the product; users own their provider relationship.
