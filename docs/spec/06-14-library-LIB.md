### 6.14 Roles, crews and project specs (LIB)

- **LIB-1 Role.** A versioned template:
  - name, category, domains and description;
  - a slug, and its seat kind: ceo (it can be the CEO), worker or reviewer;
  - optional `min_class` and whether it needs vision;
  - tool permissions: files, shell, web, browser (EXE-17), data processing, A2A (INT-11); the skills it may use, pinned by version (LIB-6);
  - the credential names it receives, and nothing else;
  - its charter text.

  A team pins a role version and can be re-pinned to the current one. Roles do not name models or effort levels. No two roles share a name. Anyone may add a role; only an admin changes one that exists, and the change is a new version.
- **LIB-2 Crew.** A named, ready-made job with a team already on it: an outcome sentence, a CEO role, teams of role plus named members, and a reference estimate of runs and tokens, which may be empty until there are real runs to take it from. A team's first named member leads it.
- **LIB-3 Libraries.** Libraries are loaded from and exported to files, and can be searched by the Founder and by MCP clients. Ship a starter library covering research, writing, engineering, data, design, review and adversary, and the plan adversary and gap reviewer.
- **LIB-4 Project spec.** One portable document that describes a project completely:
  - name, goal and project type;
  - a deadline with its source;
  - budget and quality;
  - the paying credential by name;
  - setting overrides;
  - CEO and teams;
  - standing orders;
  - controlled domains;
  - integrations needed;
  - embedded custom roles;
  - credential names with role scopes.

  **Secret values never appear in a spec, export, clone or backup of a project.**
- **LIB-5 One format.** A spec can be imported, exported from a live project, cloned, rehearsed and graded. Every surface uses this one format.
- **LIB-6 Agent Skills.** crewmind reads and writes skills in the open [Agent Skills](https://www.anthropic.com/news/donating-agent-skills-to-the-agentic-ai-foundation) format: a folder holding a `SKILL.md` (name, description, instructions) plus optional scripts, references and assets.
  - **Library.** The install keeps one skill library. The admin or a chairman adds skills from files, a Git repository or a marketplace URL. Skills are versioned, and a role pins the versions it may use (LIB-1).
  - **Review before use.** A new skill, or a new version, is shown with every file, every script, and any network address or credential name its scripts mention. The admin or chairman approves it before any role can use it. No outside source is trusted by default.
  - **Progressive loading.** A run's context pack lists only the name and description of each skill its role grants. The full instructions load when the agent activates a skill, and resources load only when the instructions reference them. Harnesses that load skills natively do so; for the others, the agent API serves them.
  - **No new powers.** A skill cannot grant a tool, permission, credential or budget its role lacks. Its scripts run inside the run's sandbox, with the role's permissions, and count toward the run's caps.
  - **crewmind's own know-how ships as skills.** The Founder doctrine, the goal grammar, grilling (FND-15) and the communication standard (MSG-12) are published as skills in this format, so other tools can use them too.
  - **Skills from experience.** The CEO may propose a new skill drafted from mistake-report lessons or repeated work. It goes through the same review before use.
