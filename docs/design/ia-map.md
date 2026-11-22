# Information architecture

## Before

One project page with thirteen equal buttons in a row: Desk, Files, Activity, Search, Budget, Models, Settings, Runs, Memory, Board, Plan, Commands, Turn on alerts and Dark theme. Panels opened as a narrow column that squeezed the chat. The project list and the Desk were separate pages with their own bars.

## After

```
Sidebar (desktop) / tab bar (phone)
├── Home                       what needs me, across every project  (badge = desk count)
│     ├── Needs you            decision cards, soonest first, one-click actions
│     ├── Projects at a glance state, who is working, budget
│     └── While you were away  the daily brief, folded
├── Projects                   every project as a card; start one (Founder or form)
│     └── <Project>
│           ├── Chat           the conversation (default) + rail: needs you, crew, budget
│           ├── Overview       goal & progress, budget burn & projection, crew, timeline, latest deliverables
│           ├── Work           Plan | Board
│           ├── Crew           org view; agent sheet: model, runs, files, "Message"
│           ├── Deliverables   gallery with inline previews; file sheet with versions and compare
│           └── More ▾         Activity · Search · Budget · Runs · Memory · Models · Settings
├── Settings                   Profile & appearance · Notifications · Models & keys · Founder · People · Defaults
└── User menu                  Theme (System / Light / Dark) · Alerts · Settings · Sign out
⌘K palette                     every place, every tool, every chat command, every project
/welcome                       first-run setup (full screen)
```

Primary destinations: **Home** and **Projects** (plus Settings). Everything else is at most two clicks away (a project tab, or More), or one keystroke away in ⌘K.

## Where each old button went

| Old button | New home | Also reachable |
| --- | --- | --- |
| Desk | **Home** (the inbox); the project header's "N decisions for you" opens this project's part | Sidebar and tab-bar badge; ⌘K "Home" |
| Files | **Deliverables** tab (gallery with previews) | A file link in the chat opens the docked Files panel; ⌘K "Open Files" |
| Activity | **Overview** timeline | More → Activity; ⌘K |
| Search | **⌘K** | More → Search |
| Budget | **Overview** burn chart; header budget meter | More → Budget; header meter opens it |
| Models | **Crew** (each agent's model in its sheet); **Settings → Models & keys** | More → Models |
| Settings | **More → Settings** (project); **Settings** (install, people, you) | ⌘K |
| Runs | **Crew** (each agent's runs, as sentences) | More → Runs; "How this was made" on a message |
| Memory | **More → Memory** | ⌘K |
| Board | **Work** tab → Board | ⌘K "Open Board" |
| Plan | **Work** tab → Plan | ⌘K "Open Plan"; Overview progress |
| Commands | **⌘K** (sidebar search button shows the shortcut) | Top bar search icon on phones |
| Turn on alerts | A **contextual prompt** on Home when there are live projects; **user menu**; **Settings → Notifications** | — |
| Dark theme | **User menu** (System / Light / Dark, following the system by default); **Settings → Profile & appearance** | ⌘K |

## Routes

| Route | Page |
| --- | --- |
| `/` | Home |
| `/desk` | redirects to `/` |
| `/projects` (`?new=form`) | Projects (with the form open) |
| `/projects/:id` | Project, Chat |
| `/projects/:id/overview` · `work` · `crew` · `deliverables` | Project tabs (deep-linkable) |
| `/draft`, `/draft/:id` | Start a project with the Founder |
| `/settings/:section?` | Settings |
| `/welcome` | First-run setup |
| `/signin`, `/accept/:token` | Signing in, setting a password |
