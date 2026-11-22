/**
 * The company made visible: the chairman, the CEO, and each team with its members (CHAT-12,
 * CHAT-18, EXE-4). Each agent is a card with what it is doing now and what it has used; a card
 * opens the agent's sheet.
 */
import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { Users } from "lucide-react";
import type { Header } from "../api/client";
import { useAuth } from "../auth";
import { ErrorNote } from "../components/common";
import { fromNow, tokens } from "../lib/humanize";
import { crew } from "../strings.crew";
import { Avatar } from "../ui/Avatar";
import { Skeleton } from "../ui/Skeleton";
import { Pill } from "../ui/Status";
import { AgentSheet } from "./AgentSheet";
import { useCrew } from "./data";
import { orgTree, statusCounts, type CrewMember } from "./logic";
import { STATUS_TONE } from "./tone";

/** Seats already shown once this session, so the entrance plays only when a seat first appears. */
const seen = new Map<string, Set<string>>();

interface Props {
  projectId: string;
  changes: number;
  header: Header | null;
  onMessage(name: string): void;
  onOpenRun(runId: string): void;
}

function AgentCard({
  member,
  fresh,
  order,
  featured = false,
  onOpen,
}: {
  member: CrewMember;
  fresh: boolean;
  order: number;
  featured?: boolean;
  onOpen(): void;
}): JSX.Element {
  const status = crew.status[member.status] ?? member.status;
  return (
    <button
      type="button"
      className={`crew-card status-${member.status}${featured ? " featured" : ""}${fresh ? " is-new" : ""}`}
      style={fresh ? ({ "--i": order } as CSSProperties) : undefined}
      onClick={onOpen}
      data-testid="crew-card"
      aria-label={crew.open(member.name, member.role)}
    >
      <span className="crew-card-top">
        <Avatar name={member.name} size={featured ? "xl" : "lg"} status={member.status} />
        <span className="crew-card-who">
          <span className="crew-card-name">{member.name}</span>
          <span className="crew-card-role">
            {member.lead ? <span className="badge">{crew.lead}</span> : null}
            {member.role}
          </span>
        </span>
        <Pill tone={STATUS_TONE[member.status]} live={member.status === "working"}>
          {status}
        </Pill>
      </span>
      <span className="crew-card-now">{member.now}</span>
      <span className="crew-card-meta tabular">
        <span>{crew.tokensUsed(tokens(member.tokens))}</span>
        <span aria-hidden="true">·</span>
        <span>{crew.runs(member.runs)}</span>
        <span aria-hidden="true">·</span>
        <span>
          {member.status === "working"
            ? crew.activeNow
            : member.lastActive
              ? crew.lastActive(fromNow(member.lastActive))
              : crew.neverActive}
        </span>
      </span>
    </button>
  );
}

function CrewSkeleton(): JSX.Element {
  return (
    <div className="crew-org" aria-busy="true">
      <Skeleton lines={1} label={crew.loading} />
      <div className="crew-grid">
        {[0, 1, 2].map((index) => (
          <div key={index} className="crew-card skeleton-card" aria-hidden="true">
            <span className="skeleton crew-skel-avatar" />
            <span className="skeleton line" />
            <span className="skeleton line" style={{ width: "60%" }} />
          </div>
        ))}
      </div>
    </div>
  );
}

export function CrewView({ projectId, changes, header, onMessage, onOpenRun }: Props): JSX.Element {
  const { person } = useAuth();
  const data = useCrew(projectId, changes, header);
  const [open, setOpen] = useState<string | null>(null);
  const members = data.members;
  const tree = useMemo(() => (members ? orgTree(members, data.teams) : null), [members, data.teams]);
  const counts = members ? statusCounts(members) : null;

  const known = seen.get(projectId) ?? new Set<string>();
  useEffect(() => {
    if (!members) return;
    const set = seen.get(projectId) ?? new Set<string>();
    for (const member of members) set.add(member.name);
    seen.set(projectId, set);
  }, [members, projectId]);

  let order = 0;
  const card = (member: CrewMember, featured = false): JSX.Element => {
    const fresh = !known.has(member.name);
    return (
      <li key={member.name}>
        <AgentCard member={member} fresh={fresh} order={fresh ? order++ : 0} featured={featured} onOpen={() => setOpen(member.name)} />
      </li>
    );
  };

  const selected = members?.find((member) => member.name === open);

  return (
    <section className="crew" aria-labelledby="crew-title" data-testid="crew-view">
      <header className="crew-head">
        <div>
          <h2 id="crew-title">{crew.title}</h2>
          <p className="quiet">{crew.intro}</p>
        </div>
        {counts ? (
          <p className="crew-summary tabular" aria-live="polite">
            {crew.summary(counts.working, counts.waiting, counts.blocked, counts.idle)}
          </p>
        ) : null}
      </header>

      {data.error && !members ? (
        <div className="stack">
          <ErrorNote error={data.error} />
          <div>
            <button type="button" className="button small" onClick={data.reload}>
              {crew.retry}
            </button>
          </div>
        </div>
      ) : null}
      {!members && !data.error ? <CrewSkeleton /> : null}

      {tree && members && members.length === 0 ? (
        <div className="empty crew-empty">
          <span className="empty-icon">
            <Users size={22} aria-hidden="true" />
          </span>
          <p className="empty-title">{crew.emptyTitle}</p>
          <p className="quiet">{crew.emptyNext}</p>
        </div>
      ) : null}

      {tree && members && members.length > 0 ? (
        <div className="crew-org">
          <div className="crew-tier crew-tier-top">
            <div className="crew-chairman">
              <Avatar name={person?.name ?? crew.you} kind="person" size="md" />
              <span>
                <span className="crew-card-name">{person?.name ?? crew.you}</span>
                <span className="crew-card-role">
                  {crew.chairman} · {crew.you}
                </span>
              </span>
            </div>
          </div>
          {tree.ceo ? (
            <>
              <span className="crew-link" aria-hidden="true" />
              <ul className="plain crew-tier">{card(tree.ceo, true)}</ul>
            </>
          ) : null}
          {tree.teams.length > 0 || tree.others.length > 0 ? <span className="crew-link" aria-hidden="true" /> : null}
          <div className="crew-groups">
            {tree.teams.map((team) => (
              <section key={team.name} className="crew-team" aria-labelledby={`crew-team-${team.name}`}>
                <h3 id={`crew-team-${team.name}`} className="crew-team-head">
                  <span>{crew.teamLabel(team.name)}</span>
                  <span className="quiet">{crew.teamCount(team.members.length + (team.lead ? 1 : 0))}</span>
                </h3>
                <ul className="plain crew-grid">
                  {team.lead ? card(team.lead) : null}
                  {team.members.map((member) => card(member))}
                </ul>
              </section>
            ))}
            {tree.others.length > 0 ? (
              <section className="crew-team crew-others" aria-labelledby="crew-others">
                <h3 id="crew-others" className="crew-team-head">
                  <span>{crew.others}</span>
                  <span className="quiet">{crew.othersHint}</span>
                </h3>
                <ul className="plain crew-grid">{tree.others.map((member) => card(member))}</ul>
              </section>
            ) : null}
          </div>
          {tree.former.length > 0 ? (
            <details className="crew-former">
              <summary>{crew.former(tree.former.length)}</summary>
              <ul className="plain crew-grid">{tree.former.map((member) => card(member))}</ul>
            </details>
          ) : null}
        </div>
      ) : null}

      {selected ? (
        <AgentSheet
          projectId={projectId}
          changes={changes}
          member={selected}
          runs={data.runs}
          onClose={() => setOpen(null)}
          onMessage={(name) => {
            setOpen(null);
            onMessage(name);
          }}
          onOpenRun={(runId) => {
            setOpen(null);
            onOpenRun(runId);
          }}
        />
      ) : null}
    </section>
  );
}
