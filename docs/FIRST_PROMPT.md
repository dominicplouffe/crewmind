# First prompts for Claude Code

Paste these one at a time, in order. Wait for each to finish and review its output before the next.

## 1. Review the spec (phase 0, no code)

```
Read CLAUDE.md, docs/PLAN.md and every file in docs/spec/. Do not write any code.

Review the spec the way a senior engineer would before building it, and write docs/spec-review.md with:
1. Contradictions between requirements, or between requirements and the principles or invariants.
2. Requirements that are ambiguous or cannot be tested as written.
3. State transitions referenced in requirements but missing from section 7, or the reverse.
4. Settings used without being in Appendix A, or listed but never used.
5. Anything in phases 0–7 that depends on a phase 8 requirement.

For each item give the spec reference, a quote, the problem, and your recommended fix. Mark blocking items (they must be decided before phase 1). Then interview me about the blocking items one at a time, each with your recommended answer, and apply the answers to docs/spec/ with CHANGELOG lines.
```

## 2. Bootstrap (phase 0)

```
Plan phase 0 bootstrap from docs/PLAN.md and write docs/phases/phase-0-plan.md. Show me the plan before building. Then build it: uv project, ruff, pyright strict, pytest with Hypothesis, CI on SQLite and Postgres, the empty operation catalog with the conformance test wired to API, CLI and MCP adapters, the attack-test harness, a mock harness stub, and the settings registry loaded from Appendix A. Finish when the phase 0 exit criteria pass.
```

## 3. Each later phase

```
Plan phase N from docs/PLAN.md. Read only the always-read spec files and the files that phase needs. Write docs/phases/phase-N-plan.md: modules, operations, tables, the tests to write first, and open questions. Then interview me on the plan before writing code.
```
