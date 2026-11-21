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
It includes axe-core scans (WCAG 2 A and AA) of the sign-in page, the project list and the
project page in both themes, and a 390 px phone run. Set `CREWMIND_E2E_PORT` to change the port and
`CREWMIND_E2E_SKIP_BUILD=1` to reuse an existing `dist`. Playwright is pinned to the version
whose Chromium is already installed; do not run `playwright install`.

## Layout

```
src/api/         generated schema, typed client, live stream (SSE), uploads
src/chat/        chat state, header strip, messages, action cards, composer
src/panels/      files and previews, compare, budget, models, settings, runs, search, activity, thread
src/components/  shared pieces, command palette, theme and alerts controls
src/lib/         markdown (sanitized), CSV, diff, autocomplete, file kinds, push
src/pages/       sign in, accept a link, project list, project
src/strings.ts   every user-facing string (English), ready for translation
public/          manifest, icons (npm run gen:icons), service worker
e2e/             Playwright tests and the scripts that start and stop the test server
```
