# Design direction

Three directions were sketched against one hero screen (Home: the inbox of decisions beside the projects). Each is described by name, palette, type, a sample component and the hero.

## A. Boardroom (chosen)

- **Feel:** a calm, well-run company. Quiet neutrals, one confident accent, generous space, information set like a good report.
- **Palette:** Radix *slate* neutrals; *iris* (#5B5BD6) as the single brand accent; green, amber and red only for status. Light and dark are equals.
- **Type:** Inter Variable for everything, tabular figures for numbers; sizes from 12 to 36 px on a 4 px grid.
- **Sample component:** the decision card. A coloured edge for urgency (with the deadline in words), the question in semibold, who is asking with their avatar, the recommendation, "If you do nothing: …", then one primary action and quiet secondary ones.
- **Hero:** greeting and a one-line answer ("2 decisions wait on you"), the inbox as the main column, project cards with live squad avatars and budget meters on the right.

## B. Control room

- **Feel:** dark-first, dense, monospaced numbers, neon status colours, like an operations console.
- **Palette:** near-black canvas, green and cyan accents.
- **Type:** Inter for text, JetBrains Mono for figures.
- **Why not:** it says "you are watching machines". The product's promise is a company that works for you; the chairman should feel in control, not on call. Dense dark UIs also make light mode an afterthought, and the brief asks for two equal themes.

## C. Paper

- **Feel:** editorial: a serif display face, warm off-white paper, ink-blue accent, like a printed briefing.
- **Palette:** cream canvas, ink text, a muted blue accent.
- **Type:** a serif for headings, a humanist sans for UI.
- **Why not:** lovely for the daily brief, but it slows scanning in lists and boards, and a second typeface would have to be self-hosted under the server's CSP.

## Why Boardroom

It is the only direction that serves both halves of the promise at once: **"I'm in control"** (calm hierarchy, decisions first, honest numbers) and **"a company is working for me"** (avatars, presence, progress). It is closest to the products people already trust for daily work (Linear, Vercel, Raycast), so it needs no learning, and its single accent and Radix scales make contrast in both themes a property of the system, not of each screen.
