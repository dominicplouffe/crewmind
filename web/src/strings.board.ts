/**
 * The strings for the Board panel: tasks, audit samples, outside evidence and launches. They are part
 * of `t` in `strings.ts` (as `t.board`); they sit here to keep that file short.
 *
 * The check labels (`verified`, `reviewed`, `self-reported`, `closed unread`, `not yet checked`) come from
 * the server and are shown exactly as given. Nothing here renames them.
 */

const plural = (count: number, one: string, many: string): string => `${count} ${count === 1 ? one : many}`;

export const board = {
  tabsLabel: "Board sections",
  tabs: { tasks: "Tasks", audit: "Audit", evidence: "Evidence", launches: "Launches" },
  refresh: "Refresh",
  agentsOnly: "Agents create the work, not people. You watch it here.",
  tasks: {
    openOnly: "Open only",
    listLabel: (state: string): string => `Tasks: ${state}`,
    group: (state: string, count: number): string => `${state} (${count})`,
    emptyTitle: "No tasks yet.",
    emptyNext:
      "Agents create tasks, not people. When the CEO plans the work, each task is listed here with who holds it and whether anyone has checked it.",
    emptyOpenTitle: "No open tasks.",
    emptyOpenNext: "Every task is closed. Turn off “Open only” to see them.",
    showClosed: (count: number): string => `Show closed tasks (${count})`,
    hideClosed: "Hide closed tasks",
    heldBy: (name: string): string => `Held by ${name}`,
    team: (name: string): string => `Team ${name}`,
    /** Three failed checks block a task (WRK-8). */
    failures: (count: number): string => `failed ${count} of 3`,
    stateOf: "State",
    labelOf: "Check",
    subtask: "Subtask",
  },
  detail: {
    back: "Back to tasks",
    title: (id: number, title: string): string => `Task ${id}: ${title}`,
    state: "State",
    label: "Check",
    goal: "Goal",
    test: "Success test",
    testKinds: {
      command: "A command the platform runs.",
      observable: "Something a reviewer reads.",
    } as Record<string, string>,
    testFiles: "Test files",
    noTestFiles: "None",
    serves: "Serves",
    servesNothing: "Not stated",
    author: "Written by",
    holder: "Held by",
    nobody: "Nobody",
    team: "Team",
    evidence: "The claimant's evidence",
    noEvidence: "None yet",
    reason: "Reason",
    created: "Created",
    closed: "Closed",
    whoChecked: "Who checked it",
    audit: "Your audit",
    auditVerdict: (verdict: string): string =>
      verdict === "waiting"
        ? "This close was drawn for your audit and waits for you."
        : verdict === "failed"
          ? "You audited this close and failed it. The task stays closed."
          : verdict === "passed"
            ? "You audited this close and passed it."
            : "This close was drawn for your audit but was not reviewed in time.",
    failures: "Failed checks",
    attempts: "Attempts",
    noAttempts: "No attempts yet. An attempt is listed here each time the claimant says the task is finished.",
    attempt: (index: number, by: string, when: string): string => `Attempt ${index} by ${by}, ${when}`,
    result: (result: string): string => `Result: ${result}`,
    output: "Output of the check",
    noOutput: "The check gave no output.",
  },
  /** One plain sentence per label, for a closed task. The label itself is never reworded. */
  whoChecked: {
    verified: "The platform ran the test and it passed.",
    reviewed: "An independent reviewer read it and passed it.",
    "self-reported": "Nobody checked this: it is self-reported.",
    "closed unread": "No reviewer was left, so it closed unread.",
    "not yet checked": "It closed before anything checked it.",
  } as Record<string, string>,
  whoCheckedOther: (label: string): string => `The server labels this “${label}”.`,
  audit: {
    listLabel: "Closes drawn for you to check",
    drawn: (drawn: number, considered: number): string =>
      `${drawn} of ${plural(considered, "close", "closes")} ${drawn === 1 ? "was" : "were"} drawn for you.`,
    emptyTitle: "Nothing to audit yet.",
    emptyNext:
      "Agents create and close tasks, not people. Some closes that a reviewer read are drawn at random for you to check yourself. They will be listed here with the author's evidence.",
    task: (id: number): string => `Task ${id}`,
    evidence: "The author's evidence",
    noEvidence: "None given",
    waiting: "waiting for you",
    verdict: (verdict: string): string => `Your verdict: ${verdict}`,
    expires: (when: string): string => `Open until ${when}`,
    pass: "Pass",
    fail: "Fail",
    of: (title: string): string => `the close of ${title}`,
    noteLabel: "What you found (optional)",
    failSubmit: "Record as failed",
  },
  evidence: {
    listLabel: "Outside evidence",
    emptyTitle: "No outside evidence yet.",
    emptyNext:
      "Agents file evidence, not people. When an agent quotes a web page to support a task, the page and the quote are listed here, with whether the platform found the quote on that page.",
    pending: "not verified yet: counts for nothing",
    failure: (reason: string): string => `Why it failed: ${reason}`,
    filedBy: (name: string): string => `Filed by ${name}`,
    task: (id: number): string => `for task ${id}`,
    newTab: "(opens in a new tab)",
  },
  launches: {
    listLabel: "Side effects and launches",
    emptyTitle: "No side effects or launches yet.",
    emptyNext:
      "Agents declare these, not people. Anything an agent does outside the project is listed here. A launch leaves something running, so the platform keeps watching it until you retire it.",
    launch: "Launch",
    effect: "Side effect",
    by: (name: string): string => `Declared by ${name}`,
    key: (key: string): string => `as “${key}”`,
    fired: { yes: "It happened.", no: "It did not happen.", unknown: "Not finished yet." },
    outcome: "Outcome",
    watch: (state: string): string => `Watch: ${state}`,
    noWatch: "Watch: not started",
    watchResult: "Last result of the watch",
    retire: "Retire",
    retireOf: (what: string): string => `the launch “${what}”`,
    retireSure: "Retire this launch? Its watch ends, and it cannot be brought back.",
    retireYes: "Yes, retire it",
  },
};
