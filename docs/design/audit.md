# Audit: the redesign, checked

## Second pass (23 Nov 2026)

The first pass was judged against a near-empty project. The second was designed and checked against a busy one, seeded by `npm run demo` (web/README.md): five agents in three teams, tasks done, in review, in progress and blocked, five delivered files, about 60% of the budget spent, and a spend approval, a question and proposed scope waiting. Screenshots: `screenshots/pass2-*`.

| What was wrong after pass one | What changed |
| --- | --- |
| One decision filled a screen; titles read "Question about other", "Spend 15.00 USD" | One compact card everywhere: the ask in plain words ("Answer a question", "Approve spending $15.00?"), the agent's words as plain text, who asks and when it is due on one line, one-click primary action; the rest behind Details. Headlines for all 18 item kinds are table-tested. |
| A heads-up looked like a decision ("The CEO asks") | A quiet note with Acknowledge. |
| The same decisions appeared three times on the project page | Header count, then the most urgent two pinned above the chat (one on a phone); the rail no longer lists them. |
| Home showed one giant card | The answer first ("3 decisions wait on you, the soonest in 24 hours"), decisions grouped by urgency, J/K to move, project cards with requirements, crew and budget. |
| Timeline of internals ("Chat session 1 is now warm", "Item 7 is now open") | A timeline of what a chairman cares about, with tasks named, bursts merged and days grouped. |
| "Projected to finish in about 1 s"; five identical axis labels | Projections say what is known; time ticks never repeat and follow the span. |
| Everyone "Idle since…" | Each agent's line comes from the tasks it holds: working on, holding, waiting for review, blocked with the reason. Teams side by side in an org view. |
| Work was a list of requirement forms | Requirements as compact rows with progress and owners, then a kanban board; the rest of the plan folded below. |
| "Good evening, Admin" | ACC-8: a person sets their own name (Settings, first-run setup). |
| No signature moment | The crew assembles around the mark once, after the Founder starts a project. |

**Checks after pass two.** Python: 492 passed on SQLite and on Postgres. Web: 617 unit tests; 62 browser tests including axe (WCAG 2.2 A/AA) in both themes and a 390 px run, plus a scan of the crew-assembled dialog. Layout shift on a throttled phone: Home 0.01, Overview 0, Work 0, Deliverables 0; chat 0.02 on a desktop and 0.05–0.2 on a phone, depending on when each decision card's item arrives (fix: API proposal A-18).

## First pass

Run on 22 Nov 2026 against a mock-model server with a scripted crew (a Deliver project whose CEO proposed two requirements). Screenshots are in [screenshots/](screenshots/): `before-*` were taken before any change, `after-*` at the end, at 1440 px and 390 px, light and dark.

## Acceptance criteria

| Criterion | Status | Evidence |
| --- | --- | --- |
| The "needs you" count agrees on every surface, and tests enforce it | **Met** | Server: `test_HUM_10_CHAT_18_the_header_count_is_the_desk_count` (empty, waiting, snoozed, observer, decided) on SQLite and Postgres. Web: `src/needs/NeedsYou.test.tsx` renders the real shell and Home and compares the sidebar badge, phone tab badge, per-project sidebar badges, inbox count, summary, project cards and page title, before and after the desk changes. Browser: `desk.spec.ts` "every surface agrees…" compares the header, sidebar, Home and title with `/v1/desk/show`, and again after a decision. |
| Fresh install to a running crew entirely in the browser | **Met, with one caveat** | `/welcome`: add a key (validated with a test call), pick a tier, set the Founder, invite people (skippable), describe the goal, then the Founder drafts and starts the project. Caveat: on the mock provider the key test always fails, so setup offers "Keep it anyway" (API proposal A-17). Not tried against a real provider (no key in this environment). |
| No more than four primary destinations; everything else within two clicks or ⌘K | **Met** | Home, Projects, Settings (plus the user menu). Project tools are one tab or More → item away; every place, tool, chat command and project is in ⌘K. See [ia-map.md](ia-map.md). |
| Every agent has a name, role, avatar and live status somewhere obvious | **Met** | Crew tab (org view), the chat rail's crew strip, project cards, the header's "who is working", avatars on chat messages. Names are seat names ("CEO", "Reviewer"); person-like names are proposal A-2. |
| Progress and budget burn with a projected finish in money and time on the project screen | **Partly met** | Overview: goal → proposed → accepted → in progress → met as one bar; burn-up chart with the wall and a dashed projection; "the budget lasts about N of active work" from the measured burn rate. **No money:** budgets are tokens by spec (revision 2), and the server has no prices; shown honestly as tokens and time (proposal A-1). |
| No raw config keys, internal event names or unexplained units on default surfaces | **Met for the web app** | Settings show labels, units and ranges, with keys under "Show technical details"; runs are sentences; feed lines are worded by the server in plain sentences (and tested). Remaining raw text comes from server refusal hints that name a setting in backticks (they now say where to fix it first), and the CLI. |
| Phone: decide and reply with one thumb; the composer never covers content | **Met** | Bottom tab bar on phones; inside a project it steps aside for the conversation. The composer sits in the flow under the list (never over it), with safe-area padding, `100dvh` and `interactive-widget=resizes-content`. Decision buttons are ≥ 44 px on touch. `device.spec.ts` checks no horizontal overflow and full-screen panels at 390 px. |
| Designed empty, loading and error states on every screen | **Met** | Skeletons shaped like the content; empty states with an icon, what will appear and the next step; `ErrorNote` with the server's message and hint; "showing the last list we had" when the desk cannot refresh; offline line in chat. |
| WCAG 2.2 AA in light and dark | **Met in automated checks** | axe (wcag2a/aa, 21a/aa, 22aa) runs in the browser suite on sign-in, Home, projects, the project in every panel and Plan and Board tab, the Memory panel and dialogs, decision cards and dialogs, settings, drafting and the rehearsal report, in both themes, and on a 390 px phone: no violations. Manual checks below. Not tested with a real screen reader. |
| Deliverables previewed inline | **Met** | Gallery cards render markdown excerpts, highlighted code, image thumbnails, CSV tables and sandboxed web pages; the sheet has the full preview, versions and compare. |
| A documented design system contributors can use | **Met** | [design-system.md](design-system.md), tokens in `web/src/styles/tokens.css`, components in `web/src/ui/`, ADR-0010. |
| No primary action fails silently | **Met for the cases found** | "Start a project" with no Founder model: the start page says what is missing before you type, offers "Set up a model" (admins) or "Fill in a form instead" (members), and a failed turn now names the fix instead of "send again". Start, Hold and Resume show the server's refusal as a notice in the chat (from another tab it is posted there too, not beside the button). |

## Accessibility, by hand

- **Contrast.** Every text token was computed against its backgrounds (table in [design-system.md](design-system.md)). Three issues were found and fixed during the build: 12 px status text on soft fills (light) was 4.2:1 and is now ≥ 5.7:1; the dark-theme primary hover was 4.0:1 and is now 6.7:1; input borders use a ≥ 3:1 token (WCAG 1.4.11).
- **Keyboard.** Every flow was walked with the keyboard: skip link to content; sidebar; ⌘K palette (combobox and listbox with arrows, Enter, Esc); `g` then `h/p/s` and, in a project, `c/o/w/r/d`; `?` lists shortcuts; menus follow the WAI-ARIA menu-button pattern; sheets and dialogs trap focus and return it; scrollable regions take focus.
- **Names.** Icon-only buttons have names; buttons whose visible text differs from a label take their name from their content (WCAG 2.5.3, fixed for the user menu, budget chip and crew strip); counts carry a spoken sentence ("2 things need you").
- **Colour alone.** Status is always a word plus a dot; urgency is the deadline in words plus the edge colour; progress bars carry a text legend; the burn chart has a text summary and a hidden data table.
- **Motion.** Every animation honours `prefers-reduced-motion`; the browser tests run with it on, so scans never see a half-faded element.

## Five-second test

Not run with people. As a heuristic check, each primary screen was read for five seconds against two questions, *what needs me?* and *what is the crew doing?*:

| Screen | What needs me | What the crew is doing |
| --- | --- | --- |
| Home | The first line: "2 decisions wait on you"; the inbox is the main column, soonest first. | Project cards: avatars of working agents and "No one is working", budget meters. |
| Project (chat) | The amber chip "2 decisions for you" under the title; the rail lists them with deadlines. | The header line ("CEO: Thinking" with a live avatar), the rail's crew strip. |
| Overview | "2 proposed requirements wait for your decision" under the progress bar. | Crew section and the timeline. |
| Phone Home | Same first line and a red badge on Home in the tab bar. | Below the inbox, project cards. |

Recommendation: run a real five-second test with three to five people before calling this done.

## Performance

Throttled phone profile (390 px, 4× CPU slowdown, 10 Mbit/s, 40 ms latency), mock server, built app:

| Screen | First paint | Largest paint | Layout shift |
| --- | --- | --- | --- |
| Home | ~1.1 s | ~1.1 s | 0.000 |
| Project overview | ~1.1 s | ~1.3 s | 0.08 |
| Project chat | ~1.0 s | ~1.2 s | 0.08–0.18 |
| Projects, Work, Crew, Deliverables, Settings, Welcome | — | — | ≤ 0.04 |

- Home first measured 0.33: its parts arrived one by one. It now appears in one pass after a skeleton.
- The chat's remaining shift comes from decision cards that load their item after the message renders; their space is reserved, but the final height varies. Fix proposed: include the item in the message (API proposal A-18).
- JavaScript: main bundle 198 KB gzip, project page 61 KB gzip (lazy). Inter is one variable Latin file; other scripts' subsets load only when used.
- Animations use only `transform` and `opacity`.

## Not done, or not proven

- No money anywhere (by spec); proposal A-1.
- Display names for agents; proposal A-2.
- Not tested with VoiceOver, NVDA or TalkBack, or on a real mid-range phone.
- No five-second test with people.
- The web redesign landed as one commit, because its parts depend on each other (the shell imports every new page).
