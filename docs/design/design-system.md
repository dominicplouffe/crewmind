# Design system v1

Everything the web app looks like comes from here. To change the look, change a token; to add a screen, use the components. A hard-coded colour, size or duration in a component is a review comment.

Files: `web/src/styles/tokens.css` (tokens), `web/src/styles/base.css` (elements and shared classes), `web/src/styles/ui.css` and `web/src/ui/*.tsx` (components), `web/src/styles/shell.css` (layout).

## Tokens

Tokens come in three layers, and components use only the second:

1. **Scales**: `--slate-1…12` (neutral), `--iris-1…12` (brand), and status steps of green, amber, red and blue. Values are Radix Colors.
2. **Semantic**: what a colour is for. These are defined twice, once per theme.
3. **Legacy aliases**: `--bg`, `--surface`, `--muted`, `--border`, `--accent` and friends, mapped onto the semantic layer so older stylesheets follow the system.

### Colour (semantic)

| Token | Use | Light | Dark |
| --- | --- | --- | --- |
| `--color-canvas` | page background | #ffffff | #111113 |
| `--color-sidebar` | sidebar | slate-2 | #0d0d0f |
| `--color-surface` | cards, inputs | #ffffff | slate-2 |
| `--color-surface-raised` | sheets, menus, dialogs | #ffffff | slate-3 |
| `--color-surface-sunken` | wells, code, rails | slate-2 | #0d0d0f |
| `--color-surface-hover` / `-active` | interactive states | slate-3 / 4 | slate-4 / 5 |
| `--color-text` | body text | slate-12 | slate-12 |
| `--color-text-muted` | secondary text (≥ 4.5:1) | slate-11 | slate-11 |
| `--color-text-faint` | decoration only (< 4.5:1) | slate-10 | slate-10 |
| `--color-border` / `-subtle` | dividers | slate-6 / 4 | slate-6 / 4 |
| `--color-border-control` | input edges (≥ 3:1, WCAG 1.4.11) | slate-9 | slate-9 |
| `--color-accent` (+ `-hover`, `-text`) | primary buttons, selection | iris-9 | iris-9 |
| `--color-accent-soft` (+ `-soft-text`, `-border`) | selected, badges | iris-3 / 11 / 7 | iris-3 / 11 / 7 |
| `--color-link` | links | iris-11 | iris-11 |
| `--color-focus` | focus rings | iris-9 | iris-10 |
| `--color-success`, `-soft`, `-border`, `-solid` | done, working | green 11 / 3 / 6 / 9 | same steps |
| `--color-warning`, … | needs attention, soon | amber 11 / 3 / 6 / 9 | same steps |
| `--color-danger`, … | overdue, errors, destructive | red 11 / 3 / 6 / 9 | same steps |
| `--avatar-1…8-bg/fg` | agent avatars | 8 hue pairs, each ≥ 4.5:1 | 8 hue pairs |

**Contrast (checked).** Text tokens on canvas and surface: text ≥ 15:1, muted ≥ 5.9:1 (light) and ≥ 8.9:1 (dark), link ≥ 6.1:1 (light) and ≥ 8.4:1 (dark). White on accent 4.9:1. Status text (step 11) on its soft background ≥ 4.5:1. Control borders ≥ 3:1 on their surface. The automated axe scans in `web/e2e` check every screen in both themes.

### Type

Inter Variable (bundled, same origin), falling back to the system UI font. Numbers use tabular figures where they line up (`.tabular`, `.num`).

| Token | Size | Use |
| --- | --- | --- |
| `--text-xs` | 12 | badges, captions, eyebrows |
| `--text-sm` | 13 | secondary text, dense lists |
| `--text-md` | 14 | the UI's base size |
| `--text-base` | 15 | reading text, chat |
| `--text-lg` | 17 | section and sheet titles |
| `--text-xl` | 22 | page titles on phones, dialogs |
| `--text-2xl` | 28 | page titles |
| `--text-3xl` | 36 | onboarding headlines |

Weights: 400, 520 (medium), 600 (semibold), 680 (bold). Headings tighten tracking slightly (`--tracking-tight`, `--tracking-display`). Inputs use 16 px on touch screens so phones do not zoom.

### Space, size, radius, elevation

- **Space:** a 4 px grid, `--space-1` (4) to `--space-16` (64).
- **Controls:** `--control-sm` 32, `--control-md` 36, `--control-lg` 44 px; on coarse pointers every button is at least 40–44 px high.
- **Layout:** `--sidebar-width` 240, `--topbar-height` 52, `--tabbar-height` 60, `--content-max` 1152, `--reading-max` 736 px.
- **Radius:** 6 (small controls), 8 (controls), 12 (cards), 16 (sheets, dialogs), full (pills, avatars of people).
- **Elevation:** `--shadow-xs` (resting cards), `-sm` (selected tab), `-md` (hover, docked panels), `-lg` (menus, sheets, palette).

### Motion

Motion explains a change; it never decorates.

| Token | Value | Use |
| --- | --- | --- |
| `--duration-fast` | 120 ms | hover, press, menus |
| `--duration-base` | 200 ms | tabs, fades |
| `--duration-slow` | 320 ms | sheets, cards entering, progress |
| `--ease-out` | cubic-bezier(.2,.8,.2,1) | most transitions |
| `--ease-spring` | cubic-bezier(.34,1.4,.64,1) | the squad-hired moment only |

Named animations: `pop-in` (menus, palette), `rise-in` (cards entering), `sheet-in` / `sheet-up` (sheets), `pulse-ring` (an agent working), `shimmer` (skeletons). Under `prefers-reduced-motion: reduce` every duration drops to near zero (bottom of `base.css`).

## Icons

[Lucide](https://lucide.dev) through `lucide-react`: 1.5–2 px strokes, sized 14 (inline), 16 (buttons, menus), 18–22 (navigation). Icons are decoration (`aria-hidden`) next to a visible word; an icon-only button carries an `aria-label` and a `title`.

## Components

| Component | Where | Notes |
| --- | --- | --- |
| Button | `.button` + `primary`, `ghost`, `danger`, `small`, `large`, `icon-only` | One primary per view. `aria-pressed` styles a toggle. |
| Input, select, textarea | elements | Labelled with `.field`; hint text linked by `aria-describedby`. |
| Card | `.card`, `.card-head`, `.mini-card` | 12 px radius, resting shadow. |
| Badge, count | `.badge`, `.count` | Counts are tabular; a zero count is hidden, not shown as "0". |
| Status pill | `ui/Status.tsx` `Pill` | Dot plus word; tone is never the only signal. |
| Avatar | `ui/Avatar.tsx` | Agents are rounded squares, people circles; hue from the name; optional status dot. |
| Decision card | `desk/ItemCard.tsx`, `desk/headline.ts` | One card for every decision, everywhere. Leads with the ask in plain words ("Add to scope?", "Approve spending $15.00 a month?"), then the agent's own words as plain text, then who asks, the deadline in words and the size on one line, then the primary action. Recommendation, if-you-do-nothing, fields, notes and set-aside wait behind Details. `slim` is the one-line form; a settled card folds to one line. |
| Inbox | `home/InboxItem.tsx`, `home/logic.ts` | Decision cards grouped by urgency (Overdue, Next 24 hours, This week, Later); J and K move between them. |
| Needs stack | `project/NeedsStack.tsx` | The most urgent decisions pinned above the conversation (two on a desktop, one on a phone), "+N more" opens the rest. |
| Note | `desk/ItemNote.tsx` | A heads-up or flag in the chat: an icon, who, their words as plain text, Acknowledge. Never a card. |
| Board | `panels/board/Kanban.tsx` | Ready, In progress, In review, Blocked (with the reason), Done; columns snap sideways on a phone. |
| Squad assembled | `squad/SquadAssembled.tsx` | The signature moment: the squad gathers around the mark once, after the Founder starts a project or on the first visit to Squad. A still card under reduced motion. |
| Agent card | `squad/` | Avatar, name, role, status, what it is doing now. |
| Progress | `ui/Progress.tsx` `SegmentBar`, `Meter` | Always paired with a text legend or label. |
| Burn chart | `overview/BurnChart.tsx` | SVG, labelled, with a text summary and a data table for screen readers. |
| Sheet | `ui/Sheet.tsx` | `<dialog>`: focus trapped, Esc closes; right side on desktop, bottom sheet on phones. |
| Menu | `ui/Menu.tsx` | WAI-ARIA menu button: arrows, Home, End, Esc returns focus. |
| Tabs | `.segmented`, `.project-tab` | Segmented control for views; underline tabs for places. |
| Command palette | `components/CommandPalette.tsx` | ⌘K / Ctrl K; grouped; combobox + listbox pattern. |
| Callout | `.callout`, `.note`, `.note-error/-warning/-success` | One clear next step in `.note-actions` / `.callout-actions`. |
| Empty state | `.empty`, `.empty-icon`, `.empty-title` | Says what will appear and what to do next. |
| Skeleton | `ui/Skeleton.tsx` | Shaped like what is coming; announced once as "Loading". |
| Toast | not used | Results appear where the action was taken; live regions announce them. |

## Layout

- **Desktop (≥ 900 px):** a 240 px sidebar (search, Home, Projects, Settings, the person's projects with live dots and needs-you counts, the user menu) beside the page.
- **Phone (< 900 px):** a top bar (logo, search, user menu) and a bottom tab bar (Home, Projects, New, Settings). Inside a project the tab bar steps aside so the conversation and composer get the height.
- **Project:** a title line, a status line (needs you, who is working, next, budget), tabs (Chat, Overview, Work, Squad, Deliverables) and **More** for the rest. Tools open as a wide docked panel (640–704 px) on large screens and full screen below 1100 px. At 1280 px and wider the chat has a rail with what needs you, the squad and the budget.

## Keyboard

| Keys | Does |
| --- | --- |
| ⌘K / Ctrl K | Command palette: go anywhere, run any tool or chat command |
| Esc | Closes the palette, a menu, a sheet or a panel; stops a reply in the chat |
| Enter / Shift+Enter | Send / new line in the composer |
| ↑ in an empty composer | Brings back your last message |
| ↑ ↓ ← → | Move within menus, tabs and the palette |

## Adding to the system

1. Need a colour? Use a semantic token. If none fits, add one to **both** themes in `tokens.css` and check its contrast.
2. Need a component? Put it in `web/src/ui/` with its styles in `ui.css`, list it in the table above, and give it a keyboard path and a label.
3. Every user-facing word lives in a `strings*.ts` file.
4. Run the axe scans (`npm run e2e`): both themes must have no WCAG 2.2 A or AA violations.
