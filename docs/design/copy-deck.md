# Copy deck: internal words to human words

Every place the web app spoke in the system's internals, and what it says now. "Owner" names who
changes the string when it is outside the chat, decision card and panel surfaces. Server text (feed
lines, titles built by the server, refusals) is shown as given; rows marked *server* are proposals
for the server, not changes made in the web app.

Principles: say who did what, in a sentence; give numbers a sense of scale (compact numbers and a
share); say what happens next, in words, never by colour alone; keep raw values one click away
("Technical details") for whoever needs them.

| # | Surface | Before | After | Why |
| --- | --- | --- | --- | --- |
| 1 | Runs, list | CEO · work · finished | CEO worked on a directive | A sentence says who did what; the dots read as a log line. |
| 2 | Runs, list | notice: directive issued | a directive | The reason is the object of the sentence, not a notice kind. |
| 3 | Runs, list | notice: project started | the new project | Same: what the run was about, in words. |
| 4 | Runs, list | notice: slow start | a slow start | Same. |
| 5 | Runs, list | message 12 from a person | your message | The chairman is the person; ids mean nothing here. |
| 6 | Runs, list | unread messages | new messages | Plain word for the same thing. |
| 7 | Runs, list | heartbeat | its regular check-in | "Heartbeat" is an implementation term. |
| 8 | Runs, list | 22 Nov 2026, 22:14 · 240 tokens · mock-frontier | finished 4 minutes ago · 240 tokens · mock-frontier | Relative time answers "how recent"; the state joins the time. |
| 9 | Runs, states | finished / failed / killed / terminated / reaped / queued / leased | finished … ago / failed … ago / stopped … ago / cut off … ago / timed out … ago / waiting to start / starting | State-machine names become what happened to the run. |
| 10 | Runs, list | (raw kind, state, reasons on every row) | Technical details (disclosure with run id, kind, state, reasons, model, attempt, times) | Raw values stay available without crowding every row. |
| 11 | Run trace | CEO: work run | CEO worked on a directive | Same sentence as the list, so the two match. |
| 12 | Run trace | State: finished | What happened: finished 4 minutes ago | Label and value in plain words. |
| 13 | Run trace | Why it ran: notice: directive issued | Why it ran: a directive | Reasons in words; the raw list is in Technical details. |
| 14 | Budget | 1,920 of 20,000,000 tokens used (0%) | 1.9K of 20M tokens used (<0.1%) | Compact numbers give scale; "0%" was false for a non-zero spend. |
| 15 | Budget | (bare progress bar) | Meter with marks at the warning and wrap-up levels, and "18M tokens left" | Shows where the limits sit, and what is left, at a glance. |
| 16 | Budget | Warning at 16,000,000 tokens | At 16M tokens (80%) the CEO is warned and a line goes in the chat. | Says what happens at the level, not only where it is. |
| 17 | Budget | Wrap-up at 18,000,000 tokens | At 18M tokens (90%) the crew wraps up: no new scope, only work already under way, and you are asked whether to raise the budget or let the project land. | "Wrap-up" was jargon; this is GOV-3 in words. |
| 18 | Budget | Limit 20,000,000 tokens | At 20M tokens all work stops until you raise the limit. | The wall's consequence, said once. |
| 19 | Budget | Tokens by kind | Where the tokens went | Asks the question the table answers. |
| 20 | Budget | Input | Reading (what the agents were given) | "Input tokens" is model-API language. |
| 21 | Budget | Output | Writing (what the agents wrote) | Same. |
| 22 | Budget | Cache writes | Saved for reuse | Same. |
| 23 | Budget | Cache reads (not counted) | Reused (not counted) | Same; the note under the table still says they do not count. |
| 24 | Models | Quality: balanced | Quality: balanced, with "Balanced: the CEO, leads and reviewers think with the strongest models; workers use mid-size models for everyday work." | The dial was named but never explained (LLM-3). |
| 25 | Models | Asked for: frontier, high effort | A top-tier model, careful thinking | Class and effort names are lineup internals. |
| 26 | Models | (seat kind not shown, or "ceo" / "reviewer") | CEO / Project Manager, or "Checks the work" | Says what the seat is for. |
| 27 | Decision card | proposed scope (tag) | Scope proposal | Kind names become what the decision is. |
| 28 | Decision card | open (tag) | (hidden; kept for screen readers) | Every card that asks is open; the tag added noise. |
| 29 | Decision card | verdict | Verdict needed | Says that something is asked of you. |
| 30 | Decision card | approval: spend | Spending approval | Colon-namespaced kind becomes a noun phrase. |
| 31 | Decision card | approval: tool permission | Tool permission | Same. |
| 32 | Decision card | approval: capacity | Capacity request | Same. |
| 33 | Decision card | audit sample | Spot check | Plain word for a random check of finished work. |
| 34 | Decision card | assist | Needs your hands | An agent needs a human step (a code, a login). |
| 35 | Decision card | delivery sign-off / reserve draw / proposed commitment | Sign-off / Reserve request / Finish date proposal | Same. |
| 36 | Decision card | Answer by Nov 25, 2026, 10:14 PM. If you do nothing: it is declined. | Decide by Wed 10:14 PM · in 3 days, then (after the recommendation) If you do nothing: it is declined. | Short date plus distance; the default outcome gets its own line. |
| 37 | Decision card | (no urgency) | Overdue / Due today / Due soon badge, plus "Overdue · was due …" | Urgency in words, not colour alone (WCAG 1.4.1). |
| 38 | Decision card | (who asks not shown) | The CEO asks / An agent asks / crewmind asks, with the asker's avatar | The chairman should know who wants the decision. |
| 39 | Decision card | Recommendation: Accept requirement 1 into scope. | RECOMMENDATION callout | The recommendation is the most useful line; it is set apart. |
| 40 | Decision card | defaulted / void (state tags) | Decided by default / No longer needed | State names become outcomes. |
| 41 | Decision card, Desk | (none) | Discuss in chat | A way to talk it over before deciding. |
| 42 | Plan, requirement | proposed (tag) | Proposed pill, and "Needs you" when it is on your desk, else "The CEO decides" | Makes clear who must act (the server decides authority). |
| 43 | Plan, requirement | checking (tag) | Being checked pill, and "Needs you" or "The reviewer decides" | Same, for verdicts. |
| 44 | Plan, requirement | met / in progress | Met / In progress pills with colour and dot | Same word, now scannable. |
| 45 | Board | ready (3) | Ready (3), task state as a pill | Sentence case; state scannable. Check labels stay the server's words (rule in strings.board.ts). |
| 46 | Memory | Project: 34 of 6,000 tokens (bare progress bar) | Project: 34 of 6,000 tokens · 1%, with a meter | Adds the share; the sentence is kept. |
| 47 | Activity | 22 Nov 2026, 22:14 (per line) | 22 minutes ago, grouped under "Sunday, November 22" | Relative time and day headings are how people scan a feed. |
| 48 | Activity | (actor id hidden or shown raw) | Your avatar, "Someone in the project", or the crewmind mark | Who did it, without showing ids. |
| 49 | Activity (server, done) | project: created (project 375c76…). / item: state changed (item 3). | The project was created. / Item 3 is now open. / CEO joined the crew. | Event names are not sentences. Changed in the server's feed wording, with a test that no line reads like an event name. |
| 50 | Chat | crewmind · crewmind · 10:14 PM (dashed box) | Centred quiet line with an icon: "Directive 1 to CEO: Plan the landing page. · 30 minutes ago" | Platform lines are context, not conversation. |
| 51 | Chat | CEO · agent · 10:14 PM | CEO · CEO / Project Manager · 5 minutes ago, with an avatar | The role says who this agent is; "agent" said nothing. |
| 52 | Chat | Admin (on your own messages) | You | Your own messages are yours; the account name is noise. |
| 53 | Chat | Delivered (text) | ✓✓ Delivered | Same word, quieter, with a mark. |
| 54 | Chat, composer | Message. / for commands, @ for agents | Message the crew… / for commands, @ to mention | Says who you are writing to. |
| 55 | Chat, composer | Enter sends. Shift+Enter starts a new line. Up arrow brings back your last message. Esc stops a reply. | Enter to send · Shift+Enter for a new line · ↑ for your last message · Esc stops a reply | Shorter, scannable, and quieter under the box. |
| 56 | Chat, composer | Attach files / Edit and resend last / Send (text buttons) | Paperclip, history and arrow icon buttons with the same accessible names | Less chrome around the box; names unchanged for assistive tech. |
| 57 | Chat | Reply · Open thread · How this was made · More (underlined links on every message) | A small toolbar on hover or focus (always shown on touch screens) | Actions stop competing with the words. |
| 58 | Chat | writing… | Writing…, with a typing indicator and the agent's avatar | Sentence case; motion shows it is live. |
| 59 | Chat, proposal | About 1,000 tokens. It cannot be undone. | Proposal · CEO proposes, then "About 1,000 tokens" and "It cannot be undone." with a warning mark | Who proposes, the cost, and the risk on separate, scannable lines. |
| 60 | Header (owner: shell) | Waiting on you: Nothing | Nothing needs you (or "2 decisions for you") | "Waiting on you: Nothing" reads as a broken label. |
| 61 | Nav (shell) | Desk (0) | Home, with a count badge only when something needs you; the header says "2 decisions for you" or "Nothing needs you" | "Desk" was an internal room name, and a zero in brackets looked like an error. |
| 62 | Account (shell) | Admin (plain text beside the buttons) | An avatar, the name and the role ("Admin" or "Member") in the user menu | The person is shown as a person. The seeded name stays "Admin" until renaming exists (API proposals). |
| 63 | Settings (settings) | run.concurrency = 4 | Agents working at once: 4 (the key under "Show technical details") | Raw setting keys are registry ids, not labels. |
| 64 | Settings (owner: settings) | Allowed: 10–360 min. The value is in seconds. | Between 10 minutes and 6 hours. | The range and the unit disagreed, and "seconds" is storage detail. |
| 65 | Founder | marker tags (words, answer, assumption, present, weak, missing) | Badges with tone: your words / your answer in accent, assumption dashed, grade present / weak / missing in green / amber / red with the word | Same words, now scannable. |
