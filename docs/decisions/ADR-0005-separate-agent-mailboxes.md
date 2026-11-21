# ADR-0005: Each agent with email gets its own mailbox account

- **Status:** Accepted (21 Nov 2026, owner: Dominic)
- **Spec:** INT-6, INT-10

## Context

The owner chose separate accounts over aliases on one project mailbox.

## Decision

In managed mode the platform creates one account per agent on the connected mail server (Stalwart first); in manual mode the chairman enters each agent's account; install-alias mode has no agent addresses. Stand-down disables, recall re-enables, delete removes.

## Consequences

More IMAP connections per project; the provisioner manages more accounts.
