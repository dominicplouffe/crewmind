## 3. Actors and authority

There are three kinds of actor: people, machines acting for people, and agents. The platform also acts, through scheduled automatic state changes. Authority flows downward; no actor can grant itself more.

| Actor | Kind | May | May never |
| --- | --- | --- | --- |
| Instance admin | person | Run the install, connect Slack, mail servers and outbound mail once, manage accounts, read every project (stated openly), hand a chair on in an emergency (recorded as a break-glass action) | Decide anything on a project they do not chair |
| Chairman | person, one per project | Own the project; talk to any agent; pin standing orders, close decisions, issue directives; set goal, budget and quality; decide approvals; grant credentials and tool permissions; start, hold, stop, delete; lock artifacts; add or cut any scope | Be bypassed: decisions reserved to the chairman cannot be taken by an agent or a model client |
| Instance member | person | Create projects, becoming their chairman; act on projects where they hold a role | See or act on a project where they hold no role (INV-5) |
| Co-chair | person | Act as the chairman, except handing on the chair and deleting the project | Act after removal (the next request is refused) |
| Observer | person | Read the project, including the chat | Write anything |
| MCP client | machine for a person | What its scopes allow, on its person's projects, recorded as machine-mediated | Human-only verbs (IF-5.6); irreversible writes in one call |
| Founder | platform assistant | Interview the chairman in chat and draft a project spec | Create a project without the chairman's go-ahead, except in quick mode the chairman asked for |
| CEO | agent, one per project | Plan; propose scope and accept it when it holds plan authority; adopt the platform's projected date; hire and stand down teams within limits; create and assign tasks; post to the project chat; act on its own plan without asking; draw the CEO reserve to finish nearly-done work (GOV-10) | Mark work done or give verdicts; write a date; change anything P7 reserves; exceed a cap; ask the chairman to decide a verb it holds (HUM-4) |
| Lead | agent | Run a team: break down claimed tasks, assign within the team, review | Act outside its team or project |
| Worker | agent | Claim and do tasks, publish artifacts, file evidence, message, use granted tools and credentials; answer the chairman when addressed | Complete a task without verification; reach data or credentials not granted to its role |
| Reviewer seat (editor, skeptic, adversary, plan adversary, gap reviewer) | agent | Review and reject others' work; give verdicts on observable tests; attack the plan; file gap reviews | Review its own work |
| Platform (dispatcher, scheduler, verifier, gateway) | system | Wake agents, meter tokens, reap dead runs, enforce caps, run checks and watches, project dates, raise flags, pause projects, build reports | Spend a token without a ledger line |

**Org shapes.** A project's org is one of three shapes, computed from the roster at creation and recorded:

- **Solo:** one agent plans and does the work. A reviewer seat does neither, so a CEO with only a reviewer is still solo; a project stops being solo when a lead or worker seat is active. A solo project works from start to finish: the CEO creates its own tasks, claims them and does them, and the platform's check or the reviewer seat closes them. With independent read turned off it is one agent: the reviewer seat the platform staffed is stood down, and observable work closes as self-reported.
- **CEO + team:** flat; the CEO talks to individuals.
- **CEO + leads + workers:** the full hierarchy. A team with a single member leads itself.

**Instance roles.** Every person is an instance `admin` or `member` (ACC-5). Admins also have every member right. In section 7, "Chairman" in a Who column means the chairman or a co-chair, except for deleting the project and handing on the chair.

**Authority dial.** Six per-project settings decide who holds each delegable verb (Appendix A):

1. `authority.accept_scope`: accepting CEO-proposed scope into the plan.
2. `authority.change_scope`: changing CEO-proposed scope (cut, reword, re-estimate, restage).
3. `authority.date`: adopting the platform's projected date as the commitment. Nobody but the chairman ever writes a date.
4. `authority.verdict`: giving verdicts on observable tests.
5. `authority.credential_rescope`: re-scoping existing credentials across roles.
6. `authority.reserve_draw`: drawing the CEO reserve to finish nearly-done work (GOV-10).

There are two presets, set with `authority.preset`. Choosing a preset writes all six verb settings in one change. Changing a verb setting on its own makes the preset `custom`:

- **Autonomous** is the default. Verbs 1, 2, 3, 5 and 6 go to the CEO. Verdicts (verb 4) go to an independent reviewer seat, never the CEO (P5).
- **Supervised** gives all six to the chairman.

Every CEO use of a delegated verb is audited, shown in the chat activity feed, and reversible by the chairman.

**Never delegable**, at any setting: the goal; standing orders; closed decisions; budget, quality and every other setting; chairman-authored scope; creating a credential; allowing a write-capable data-source tool; the email allowlist; real-world spend approvals; legal approvals; stopping or deleting the project.
