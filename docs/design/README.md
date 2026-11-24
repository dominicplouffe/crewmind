# Nightsquad design

The web app's design: what it should feel like, the system it is built from, and why.

| Document | What it holds |
| --- | --- |
| [design-direction.md](design-direction.md) | Three directions considered, the one chosen, and why |
| [design-system.md](design-system.md) | Tokens, type, colour, spacing, motion, icons and the components, for contributors |
| [brand.md](brand.md) | The logo and wordmark |
| [ia-map.md](ia-map.md) | The navigation, and where each of the old thirteen buttons went |
| [copy-deck.md](copy-deck.md) | Every internal-speak string replaced, before and after |
| [api-proposals.md](api-proposals.md) | Data the design would use that the server does not give yet |
| [audit.md](audit.md) | Accessibility audit, five-second tests, performance, before/after screenshots |

## Principles

1. **Truth first.** One source for "needs you": the server's desk (HUM-10). Every badge, count, header and page title reads it. If data is stale or loading, the page says so.
2. **Decisions over data.** Each screen answers "what should I do next?" before "what happened?".
3. **Show the company.** Agents have a name, a role, an avatar and a live status. Warm, never cartoonish.
4. **Plain language.** No raw keys, internal event names or unexplained units on a default surface. Internals sit behind "Technical details".
5. **Calm by default, rich on demand.** Quiet defaults, depth one click away.
6. **Every state is designed:** empty, loading, partial, error, offline, first run, all done.
7. **Fast and keyboard-first** on a desktop, **thumb-first** on a phone.
8. **Accessible by construction:** WCAG 2.2 AA in both themes, never colour alone, reduced motion honoured.
9. **Open-source friendly:** tokens and components documented, no proprietary dependencies.
