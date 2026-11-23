# crewmind web app

The browser client for crewmind: TypeScript + React, built with Vite. It holds no business rules:
it calls the API and shows what comes back, including the server's own refusal messages and hints.

## Develop

```bash
npm install
npm run dev          # http://localhost:5173
```

The dev server proxies `/v1`, `/files`, `/stream` and `/healthz` to a crewmind server at
`http://127.0.0.1:8433`. Set `CREWMIND_API` to use another address. To start a throwaway server
with the mock model (no paid calls):

```bash
e2e/start-backend.sh 8433 /tmp/crewmind-dev   # prints when ready; setup link is in <dir>/setup.json
e2e/stop-backend.sh /tmp/crewmind-dev
```

To see the app with a crew at work, seed a busy demo project on that throwaway server (five agents,
tasks in every state, delivered files, half the budget spent, decisions waiting):

```bash
npm run demo -- http://127.0.0.1:8433 /tmp/crewmind-dev
```

## Build

```bash
npm run build        # type-checks, then writes web/dist
```

The Python server serves `web/dist` at `/` on the same origin as the API, under a strict
Content-Security-Policy (no inline scripts, no external hosts). `sw.js` and
`manifest.webmanifest` sit at the root of `dist`.

## API types

`src/api/schema.d.ts` is generated from `openapi.json`. Do not edit it by hand.

```bash
npm run gen:api      # after openapi.json changes
```

`src/api/client.ts` derives every request and response type from that file.

## Tests

```bash
npm run lint         # ESLint with the TypeScript and jsx-a11y plugins
npm test             # Vitest unit tests (no server, no network)
npm run e2e          # Playwright against a real server with the mock model
```

`npm run e2e` builds the app, starts a server on port 8455 with `e2e/start-backend.sh`
(data in `e2e/.run`, removed on each start), runs the tests in Chromium, and stops the server.
It includes axe-core scans (WCAG 2 A and AA) of the sign-in page, the project list, the
project page, the Memory panel and every Board tab in both themes, and a 390 px phone run. `e2e/listening.spec.ts`
covers standing orders, decisions, corrections, examples, memory and history paging; the test
server uses the in-process memory engine, whose search matches by shared words. `e2e/board.spec.ts`
covers the Board: only agents create tasks, so it scripts the mock CEO and Reviewer (`CEO.work.json`,
`Reviewer.work.json` in `e2e/.run/scripts`, see `setWorkScript` in `e2e/helpers.ts`) and starts each CEO
work run with a `/do` directive. Set `CREWMIND_E2E_PORT` to change the port and
`CREWMIND_E2E_SKIP_BUILD=1` to reuse an existing `dist`. Playwright is pinned to the version
whose Chromium is already installed; do not run `playwright install`.

## Design

The design system, the navigation map and the copy deck are in `docs/design/` (start with its README).
Colours, type, spacing and motion are tokens in `src/styles/tokens.css`; never hard-code one in a
component. Shared components live in `src/ui/`.

## Layout

```
src/api/         generated schema, typed client, live stream (SSE), uploads
src/shell/       the app shell: sidebar, phone tab bar, user menu, ⌘K palette, keyboard shortcuts
src/needs/       "what needs me": the one selector every count reads (HUM-10), and its tests
src/ui/          design-system components: Avatar, Pill, Sheet, Menu, Skeleton, progress, Logo
src/home/        Home's inbox items and project cards
src/project/     the project header, tabs, chat rail, work view, needs sheet
src/chat/        chat state, history paging, messages and their actions, action cards, composer
src/overview/    the project overview: progress, budget burn chart, timeline
src/crew/        the crew: org view, agent sheet, crew strip
src/deliverables/  the gallery of files with inline previews
src/settings/    Settings (profile, notifications, models and keys, Founder, people, install)
src/onboarding/  first-run setup (/welcome) and the setup status hook
src/panels/      files and previews, compare, budget, models, settings, runs, search, activity, thread
src/panels/memory/  the Memory panel: pinned memory, standing orders, decisions, corrections, recall, preferences
src/panels/board/   the Board panel: tasks and their check labels, audit samples, outside evidence, launches
src/panels/plan/    the Plan panel: scope, dates and budget, finish, decision items, agenda, rehearsal
src/founder/     drafting a project with the Founder
src/desk/        decision cards, snooze, the daily brief
src/components/  the command palette, common pieces, the theme context
src/lib/         markdown (sanitized), CSV, diff, autocomplete, file kinds, push, plain-words formatting
src/pages/       sign in, accept a link, Home, the project list, a project
src/strings*.ts  every user-facing string (English), ready for translation
public/          manifest, icons (npm run gen:icons), service worker
e2e/             Playwright tests and the scripts that start and stop the test server
```
