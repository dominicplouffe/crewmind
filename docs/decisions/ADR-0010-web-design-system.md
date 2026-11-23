# ADR-0010: A tokenised design system for the web app, with Inter and Lucide

- **Status:** Accepted (23 Nov 2026; the owner delegated the call)
- **Spec:** NFR-18 (accessibility), NFR-24 (stack), P18 (plain words), CHAT-18, CHAT-20, HUM-10

## Context

The web app worked but had no design: default grey boxes, thirteen equal buttons in one row, raw setting keys, and a header that disagreed with the desk. A redesign needs a shared visual language that contributors can extend without a designer, and that keeps the server's strict Content-Security-Policy (no external hosts, no inline scripts).

## Decision

- **Tokens in CSS custom properties** (`web/src/styles/tokens.css`): scales, then semantic tokens (`--color-surface`, `--color-text-muted`, `--color-accent`, status colours), then aliases for the older names. Colour values come from Radix Colors (MIT), whose steps are designed for WCAG contrast in light and dark. No CSS framework and no CSS-in-JS: the app already used plain CSS files, and tokens keep it that way.
- **Inter** (SIL Open Font License) is bundled with `@fontsource-variable/inter` and served from the same origin, so the CSP stays as it is. System fonts are the fallback.
- **Lucide** icons (`lucide-react`, ISC licence): one consistent, tree-shaken SVG set with React components.
- **Components** in `web/src/ui/` (Avatar, Pill, Sheet, Menu, Skeleton, progress) and the shared classes in `base.css`, documented in `docs/design/design-system.md`.

## Consequences

- Two runtime dependencies are added to `web/`: `@fontsource-variable/inter` and `lucide-react`. Both are open source with permissive licences and no network calls.
- The bundle grows by the font files (Latin variable font about 48 KB, other subsets load only when a page uses them) and by the icons actually imported.
- Every new colour must be a token; a hard-coded colour in a component is a review comment.
