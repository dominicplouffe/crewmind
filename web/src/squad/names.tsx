/**
 * How an agent is shown (EXE-18): its person-like name first, its role second. The seat name stays
 * the identity the server uses (chat authors, runs, tasks); this is the one place that maps it to
 * what a person reads. Outside a project the seat name is shown as it is.
 */
import { createContext, useContext, useMemo, type ReactNode } from "react";
import type { Seat } from "../api/client";
import { Avatar } from "../ui/Avatar";

export interface AgentName {
  /** The name it goes by: "Maya". */
  name: string;
  /** Its role, short: "CEO", "Reviewer", "Software Engineer". Empty when unknown. */
  role: string;
  /** Its seat name, the identity: "CEO". */
  seat: string;
}

export type NameOf = (seat: string) => AgentName;

/** "CEO / Project Manager" on the CEO reads "CEO"; any other role is shown as given. */
export function roleLabel(seat: Pick<Seat, "kind" | "role">): string {
  return seat.kind === "ceo" ? "CEO" : seat.role;
}

export function namesOf(seats: readonly Seat[]): NameOf {
  const known = new Map(seats.map((seat) => [seat.name, { name: seat.display_name || seat.name, role: roleLabel(seat), seat: seat.name }]));
  return (seat) => known.get(seat) ?? { name: seat, role: "", seat };
}

const plain: NameOf = (seat) => ({ name: seat, role: "", seat });
const NamesContext = createContext<NameOf>(plain);

export function AgentNamesProvider({ seats, children }: { seats: readonly Seat[] | undefined; children: ReactNode }): JSX.Element {
  const value = useMemo(() => (seats ? namesOf(seats) : plain), [seats]);
  return <NamesContext.Provider value={value}>{children}</NamesContext.Provider>;
}

/** What to type after @ to address an agent by name: the server leaves spaces out (EXE-18). */
export function mentionOf(name: string): string {
  return name.replace(/\s+/g, "");
}

/** `(seat) => { name, role }`: the seat's shown name and role, or the seat name when unknown. */
export function useAgentName(): NameOf {
  return useContext(NamesContext);
}

/** An agent's avatar: initials from the name it goes by, colour from its seat, so a rename keeps the colour. */
export function AgentAvatar({
  seat,
  size = "md",
  status = null,
  label,
}: {
  seat: string;
  size?: "xs" | "sm" | "md" | "lg" | "xl";
  status?: "working" | "waiting" | "blocked" | "idle" | null;
  label?: string;
}): JSX.Element {
  const { name } = useAgentName()(seat);
  return <Avatar name={name} hueKey={seat} kind="agent" size={size} status={status} label={label} />;
}
