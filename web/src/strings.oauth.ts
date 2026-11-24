/**
 * The strings for approving an AI client that asks to act for the person, and for the list of
 * clients they approved. They are part of `t` in `strings.ts` (as `t.oauth`).
 */

export const oauth = {
  pageTitle: "Approve an AI client · Nightsquad",
  title: "An AI client asks to act for you",
  intro:
    "A program outside Nightsquad wants to use your account. It will be able to do what you tick below, as you, until you revoke it.",
  client: "Client",
  sendsBack: "After you answer, your browser goes to",
  scopesLegend: "What it may do",
  scopes: {
    read: { name: "Read", allows: "See your projects." },
    steer: { name: "Steer", allows: "Chat, decide items, and start and hold projects." },
    create: { name: "Create", allows: "Create projects." },
    configure: { name: "Configure", allows: "Change settings, hire teams and set models." },
  } as Record<string, { name: string; allows: string }>,
  unknownScope: "Nightsquad does not know this permission.",
  noneAsked: "The client asked for no permissions.",
  noneTicked: "Tick at least one permission to approve, or deny the request.",
  approve: "Approve",
  approving: "Approving…",
  deny: "Deny",
  incompleteTitle: "This link is incomplete.",
  incompleteNext: "It does not say which client is asking or where to send you back. Start again from the AI client.",
  home: "Go to your projects",
  clients: {
    title: "AI clients you approved",
    listLabel: "AI clients you approved",
    empty: "You have approved no AI clients.",
    scopes: (names: string): string => `May: ${names}`,
    since: (when: string): string => `Approved ${when}`,
    revoke: "Revoke",
    confirm: (name: string): string => `Revoke ${name}? It stops working at once.`,
    confirmYes: "Revoke",
  },
};
