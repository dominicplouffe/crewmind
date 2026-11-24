/**
 * The strings for the project overview, its timeline, the burn chart and the chat's side rail.
 * Sentences that name people and things are built from parts: plain text, a name (`who`) and a
 * title (`title`, written by an agent or the chairman and always shown as plain text, P4).
 */

export type Part = string | { who: string } | { title: string };

const plural = (count: number, one: string, many: string): string => `${count} ${count === 1 ? one : many}`;

export const story = {
  title: "Overview",
  loading: "Loading the overview…",
  sectionError: "This part could not load.",
  retry: "Try again",

  headline: {
    label: "Where the project stands",
    lead: {
      draft: "Not started",
      starting: "Getting started",
      steady: "Under way",
      blocked: "Blocked",
      held: "On hold",
      paused: "Paused",
      ready: "Ready for sign-off",
      completed: "Complete",
      stopped: "Stopped",
      allMet: "Every requirement met",
    } as Record<string, string>,
    draft: "The project is still a draft.",
    noRequirements: "The CEO has not proposed requirements yet.",
    requirements: (met: number, active: number, total: number): string => {
      if (total > 0 && met === total) return `all ${plural(total, "requirement", "requirements")} met`;
      if (met > 0 && active > 0) return `${met} of ${plural(total, "requirement", "requirements")} met, ${active} under way`;
      if (met > 0) return `${met} of ${plural(total, "requirement", "requirements")} met`;
      return `${active} of ${plural(total, "requirement", "requirements")} under way`;
    },
    tasks: (done: number, total: number): string => `${done} of ${plural(total, "task", "tasks")} done`,
    budget: (share: string): string => `${share} of the budget used`,
    holds: {
      chairman: "you put it on hold",
      budget_wall: "the budget wall is reached",
      auth_failures: "a model provider keeps refusing its credential",
      skipped_cycles: "two cycles in a row were skipped",
    } as Record<string, string>,
    hold: (reason: string, lifts: string): string => `Because ${reason}. It lifts by ${lifts}.`,
    blockedOne: "is blocked",
    blockedMore: (count: number): string => `and ${plural(count, "other task", "other tasks")} are blocked`,
    openWork: "Open the work",
    goal: "Goal",
  },

  now: {
    title: "Now",
    label: "Who is doing what",
    empty: "Quiet right now: no task is claimed, blocked or waiting for review.",
    more: (count: number): string => `${count} more on the Work tab`,
    working: (who: string, title: string | null): Part[] =>
      title ? [{ who }, " is working on ", { title }] : [{ who }, " is at work"],
    claimed: (who: string, title: string): Part[] => [{ who }, " has ", { title }, " in hand"],
    claimedNote: "Claimed, not running at the moment",
    review: (title: string): Part[] => [{ title }, " waits for review"],
    checking: (title: string): Part[] => [{ title }, " is being checked"],
    blocked: (title: string): Part[] => [{ title }, " is blocked"],
    from: (who: string): string => `From ${who}`,
    team: (team: string): string => `Team ${team}`,
    noReason: "No reason given.",
    status: { working: "working", blocked: "blocked", review: "waiting for review", checking: "being checked", claimed: "claimed" },
  },

  progress: {
    title: "Progress",
    label: "Requirements by stage",
    openPlan: "Open the plan",
    none: "No requirements yet. The CEO proposes them once the project starts.",
    segments: { proposed: "proposed", todo: "accepted, not started", active: "in progress", done: "met" },
    states: {
      proposed: "Proposed",
      accepted: "Not started",
      "in progress": "In progress",
      checking: "Being checked",
      met: "Met",
      cut: "Cut",
      declined: "Declined",
    } as Record<string, string>,
    tasks: (done: number, total: number): string => (total === 0 ? "No tasks yet" : `${done} of ${plural(total, "task", "tasks")} done`),
    tasksLabel: (text: string, done: number, total: number): string => `${text}: ${done} of ${plural(total, "task", "tasks")} done`,
    excluded: (count: number): string => `${count} cut or declined, not shown`,
    projection: {
      measured: (span: string, when: string): string => `At the measured pace the open work takes about ${span} of active work, finishing around ${when}.`,
      bestCase: (span: string): string => `At best the open work takes about ${span} of active work.`,
      soon: "At the measured pace the open work needs only minutes of running time; what waits on people decides when it ends.",
      unknown: "Not enough finished work yet to project a finish.",
      nothingLeft: "Nothing accepted is left to do.",
      waitingOnYou: (count: number): string =>
        `${plural(count, "proposed requirement waits", "proposed requirements wait")} for a decision.`,
      raw: (text: string): string => `Projection: ${text}.`,
    },
    target: (date: string, beside: string): string => `Target: ${date}. ${beside}`,
    commitment: (state: string, date: string | null): string => (date ? `Commitment: ${date} (${state})` : `Commitment: ${state}`),
  },

  budget: {
    title: "Budget",
    open: "Budget details",
    used: (spent: string, wall: string): string => `${spent} of ${wall} tokens`,
    share: (share: string): string => `${share} used`,
    pace: (rate: string, left: string, lasts: string): string =>
      `About ${rate} tokens per active hour. The ${left} left covers about ${lasts} of active work at that pace.`,
    paceShort: (lasts: string): string => `About ${lasts} of active work left at this pace`,
    noPace: "The pace is measured once a few work runs finish.",
    atWall: "The budget wall is reached. Work is paused until you raise it.",
    meterLabel: (share: string): string => `Budget used: ${share}`,
  },

  crew: { title: "The crew", open: "Open the crew" },

  timeline: {
    title: "Timeline",
    label: "What happened, newest first",
    empty: "Nothing has happened yet.",
    seeAll: "See all activity",
    today: "Today",
    yesterday: "Yesterday",
    andMore: (count: number): string => `and ${count} more`,
    you: "You",
    project: {
      started: (who: string | null): Part[] => (who ? [{ who }, " started the project"] : ["The project started"]),
      created: (who: string | null): Part[] => (who ? [{ who }, " created the project"] : ["The project was created"]),
      resumed: "The project resumed",
      held: "The project went on hold",
      paused: "The project paused",
      ready: "The project is ready for sign-off",
      completed: "The project is complete",
      stopped: "The project was stopped",
      other: (state: string): string => `The project is now ${state}`,
    } as const,
    finished: (who: string | null, titles: string[]): Part[] => {
      const [only] = titles;
      if (titles.length === 1 && only !== undefined) return who ? [{ who }, " finished ", { title: only }] : [{ title: only }, " is done"];
      return who ? [{ who }, ` finished ${titles.length} tasks`] : [`${titles.length} tasks are done`];
    },
    blocked: (who: string | null, titles: string[]): Part[] => {
      const [only] = titles;
      if (titles.length === 1 && only !== undefined) return who ? [{ who }, " is blocked on ", { title: only }] : [{ title: only }, " got blocked"];
      return [`${titles.length} tasks got blocked`];
    },
    delivered: (who: string | null, names: string[], update: boolean): Part[] => {
      const verb = update ? "updated" : "delivered";
      const [only] = names;
      const what: Part[] = names.length === 1 && only !== undefined ? [{ title: only }] : [`${names.length} files`];
      return who ? [{ who }, ` ${verb} `, ...what] : [...what, update ? " updated" : " delivered"];
    },
    proposed: (who: string | null, texts: string[]): Part[] => {
      const [only] = texts;
      if (texts.length === 1 && only !== undefined) return who ? [{ who }, " proposed ", { title: only }] : [{ title: only }, " was proposed"];
      return who ? [{ who }, ` proposed ${texts.length} requirements`] : [`${texts.length} requirements were proposed`];
    },
    accepted: (who: string | null, texts: string[]): Part[] => {
      const [only] = texts;
      if (texts.length === 1 && only !== undefined) return who ? [{ who }, " accepted ", { title: only }] : [{ title: only }, " was accepted"];
      return who ? [{ who }, ` accepted ${texts.length} requirements`] : [`${texts.length} requirements were accepted`];
    },
    met: (texts: string[]): Part[] => {
      const [only] = texts;
      return texts.length === 1 && only !== undefined ? ["Requirement met: ", { title: only }] : [`${texts.length} requirements met`];
    },
    cut: (texts: string[]): Part[] => {
      const [only] = texts;
      return texts.length === 1 && only !== undefined ? ["Requirement cut: ", { title: only }] : [`${texts.length} requirements cut`];
    },
    declined: (texts: string[]): Part[] => {
      const [only] = texts;
      return texts.length === 1 && only !== undefined ? ["Requirement declined: ", { title: only }] : [`${texts.length} requirements declined`];
    },
    hired: (who: string | null, teams: string[]): Part[] => {
      const [only] = teams;
      const what = teams.length === 1 && only !== undefined ? `the ${only} team` : `${teams.length} teams`;
      return who ? [{ who }, ` hired ${what}`] : [`Hired ${what}`];
    },
    asked: (who: string | null, title: string): Part[] => (who ? [{ who }, " asked you: ", { title }] : ["A question for you: ", { title }]),
    approval: (who: string | null, title: string): Part[] =>
      who ? [{ who }, " asked for your approval: ", { title }] : ["Waiting for your approval: ", { title }],
    waiting: (title: string): Part[] => [{ title }, " waits for you"],
    decided: (who: string | null, title: string, outcome: string | null): Part[] => [
      ...(who ? [{ who }, " decided "] : ["Decided: "]),
      { title },
      ...(outcome ? [` (${outcome})`] : []),
    ],
    defaulted: (title: string, outcome: string | null): Part[] => [{ title }, outcome ? ` closed on its default (${outcome})` : " closed on its default"],
  },

  latest: {
    title: "Latest deliverables",
    open: "See all deliverables",
    empty: "Nothing delivered yet. Files appear here as the crew writes them.",
  },

  rail: {
    label: "The company at work",
    now: "Now",
    atWork: (count: number): string => (count === 1 ? "1 at work" : `${count} at work`),
    openWork: "Work",
    progress: "Progress",
    openPlan: "Plan",
    met: (met: number, total: number): string => `${met} of ${plural(total, "requirement", "requirements")} met`,
    inProgress: (count: number): string => `${count} in progress`,
    openActivity: "Activity",
    openBudget: "Details",
    delivered: "Just delivered",
    deliveredEmpty: "No files yet.",
    budget: "Budget",
    next: "Next",
    needs: (count: number): string => `${plural(count, "decision waits", "decisions wait")} for you`,
    review: "Review",
    overview: "Overview",
    allFiles: "All files",
  },
};

export const burn = {
  label: (spent: string, wall: string, pace: string): string => `Tokens used over time: ${spent} of a ${wall} budget. ${pace}`,
  legend: { used: "Used", projection: "At the measured pace", wall: "Budget wall", warn: "Warning", wrapup: "Wrap-up" },
  wallAbove: (wall: string): string => `Budget wall at ${wall}, far above this scale`,
  reachesWall: (when: string): string => `reaches the wall ${when}`,
  pace: (rate: string): string => `About ${rate} tokens per active hour`,
  noPace: "No pace measured yet",
  noData: "No tokens used yet. The chart fills in as the crew runs.",
  tableCaption: "Tokens used over time",
  time: "Time",
  total: "Tokens used so far",
};
