/**
 * The company made visible: the chairman, the CEO with any side seats beside it, and the teams side
 * by side, each with its members (CHAT-12, CHAT-18, EXE-4). Each agent is a card with what it is
 * doing now (from its runs and the tasks it holds) and its share of the crew's tokens; a card opens
 * the agent's sheet. When the teams no longer fit side by side, the org turns into an indented list
 * so its lines stay true.
 */
import { useEffect, useMemo, useRef, useState, type CSSProperties, type RefObject } from "react";
import { Users } from "lucide-react";
import type { Header } from "../api/client";
import { useAuth } from "../auth";
import { ErrorNote } from "../components/common";
import { AgentText } from "../panels/board/parts";
import { fromNow, share, tokens } from "../lib/humanize";
import { crew } from "../strings.crew";
import { Avatar } from "../ui/Avatar";
import { Meter } from "../ui/Progress";
import { Skeleton } from "../ui/Skeleton";
import { AgentSheet } from "./AgentSheet";
import { useCrew } from "./data";
import { SUMMARY_ORDER, orgTree, statusCounts, tokenShare, type CrewMember } from "./logic";
import { StatusFace } from "./parts";

/** Seats already shown once this session, so the entrance plays only when a seat first appears. */
const seen = new Map<string, Set<string>>();

/** Layout only: the narrowest a team column may get before the org turns into a list. */
const COLUMN_MIN_REM = 13;
/** Layout only: the gap between team columns (matches --space-4). */
const COLUMN_GAP_REM = 1;
/** Layout only: the width at which a side seat fits beside the CEO. */
const SIDE_BESIDE_REM = 50;

interface Props {
  projectId: string;
  changes: number;
  header: Header | null;
  /** The person chairs the project, so the agent sheet offers a rename (EXE-18). */
  canRename?: boolean;
  /** Start a message: `mention` is what to type after the @. */
  onMessage(mention: string): void;
  onOpenRun(runId: string): void;
  /** An agent was renamed: the page reloads the roster its names come from. */
  onRenamed?(): void;
}

/** The width of an element in rem, kept up to date as it resizes. */
function useWidthRem(ref: RefObject<HTMLElement>, shown: boolean): number | null {
  const [width, setWidth] = useState<number | null>(null);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const rem = (): number => parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
    const measure = (): void => setWidth(element.getBoundingClientRect().width / rem());
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref, shown]);
  return width;
}

function AgentCard({
  member,
  all,
  fresh,
  order,
  featured = false,
  showLead,
  onOpen,
}: {
  member: CrewMember;
  all: readonly CrewMember[];
  fresh: boolean;
  order: number;
  featured?: boolean;
  showLead: boolean;
  onOpen(): void;
}): JSX.Element {
  const part = tokenShare(member, all);
  const shareText = share(member.tokens, all.reduce((sum, one) => sum + one.tokens, 0));
  // An idle agent's sentence already says when it was last active; its runs are said instead.
  const when =
    member.status === "working"
      ? crew.activeNow
      : member.status === "idle"
        ? crew.runs(member.runs)
        : member.lastActive
          ? crew.lastActive(fromNow(member.lastActive))
          : crew.neverActive;
  return (
    <button
      type="button"
      className={`crew-card status-${member.status}${featured ? " featured" : ""}${fresh ? " is-new" : ""}`}
      style={fresh ? ({ "--i": order } as CSSProperties) : undefined}
      onClick={onOpen}
      data-testid="crew-card"
      data-status={member.status}
    >
      <span className="crew-card-top">
        <StatusFace seat={member.name} status={member.status} size={featured ? "lg" : "md"} />
        <span className="crew-card-who">
          <span className="crew-card-name">
            {member.displayName}
            {showLead ? <span className="badge">{crew.lead}</span> : null}
          </span>
          {member.roleLabel.trim().toLowerCase() !== member.displayName.trim().toLowerCase() ? (
            <span className="crew-card-role" title={member.role}>
              {member.roleLabel}
            </span>
          ) : null}
        </span>
      </span>
      <span className="crew-card-now">
        {member.now}
        {member.doing ? <span className="crew-card-doing"> · {member.doing}</span> : null}
      </span>
      {member.reason ? (
        <span className="crew-card-reason">
          <span className="visually-hidden">{crew.reason}: </span>
          <AgentText text={member.reason} />
        </span>
      ) : null}
      <span className="crew-card-foot">
        <Meter value={Math.round(part * 1000)} max={1000} label={crew.shareLabel(member.displayName, shareText)} />
        <span className="crew-card-meta tabular">
          <span>{crew.share(tokens(member.tokens), shareText)}</span>
          <span>{when}</span>
        </span>
      </span>
    </button>
  );
}

function CrewSkeleton(): JSX.Element {
  return (
    <div className="org org-columns" aria-busy="true" style={{ "--n": 3 } as CSSProperties}>
      <Skeleton lines={1} label={crew.loading} />
      <div className="org-teams">
        {[0, 1, 2].map((index) => (
          <div key={index} className="org-team" aria-hidden="true">
            <div className="crew-card skeleton-card">
              <span className="skeleton crew-skel-avatar" />
              <span className="skeleton line" />
              <span className="skeleton line" style={{ width: "60%" }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Tally({ members }: { members: CrewMember[] }): JSX.Element {
  const counts = statusCounts(members);
  const entries = SUMMARY_ORDER.map((status) => ({ status, count: counts[status] })).filter((entry) => entry.count > 0);
  return (
    <>
      <ul className="plain crew-tally" aria-label={crew.summaryLabel}>
        {entries.map((entry) => (
          <li key={entry.status} className="tabular">
            <span className={`crew-dot-inline dot-${entry.status}`} aria-hidden="true" />
            {crew.summary([entry])}
          </li>
        ))}
      </ul>
      <p className="visually-hidden" aria-live="polite">
        {crew.summary(entries)}
      </p>
    </>
  );
}

export function CrewView({ projectId, changes, header, canRename, onMessage, onOpenRun, onRenamed }: Props): JSX.Element {
  const { person } = useAuth();
  const data = useCrew(projectId, changes, header);
  const [open, setOpen] = useState<string | null>(null);
  const orgRef = useRef<HTMLDivElement>(null);
  const members = data.members;
  const width = useWidthRem(orgRef, Boolean(members && members.length > 0));
  const tree = useMemo(() => (members ? orgTree(members, data.teams) : null), [members, data.teams]);
  const current = useMemo(() => (members ?? []).filter((member) => member.state !== "stood down"), [members]);

  const known = seen.get(projectId) ?? new Set<string>();
  useEffect(() => {
    if (!members) return;
    const set = seen.get(projectId) ?? new Set<string>();
    for (const member of members) set.add(member.name);
    seen.set(projectId, set);
  }, [members, projectId]);

  const sideBeside = width === null || width >= SIDE_BESIDE_REM;
  const sideColumn = tree !== null && tree.others.length > 0 && !sideBeside;
  const columnCount = (tree?.teams.length ?? 0) + (sideColumn ? 1 : 0);
  const columns = width === null || width >= columnCount * COLUMN_MIN_REM + (columnCount - 1) * COLUMN_GAP_REM;

  let order = 0;
  const card = (member: CrewMember, options: { featured?: boolean; showLead?: boolean } = {}): JSX.Element => {
    const fresh = !known.has(member.name);
    return (
      <li key={member.name}>
        <AgentCard
          member={member}
          all={current}
          fresh={fresh}
          order={fresh ? order++ : 0}
          featured={options.featured}
          showLead={options.showLead ?? false}
          onOpen={() => setOpen(member.name)}
        />
      </li>
    );
  };

  const selected = members?.find((member) => member.name === open);
  const chairman = person?.name ?? crew.you;

  return (
    <section className="crew" aria-labelledby="crew-title" data-testid="crew-view">
      <header className="crew-head">
        <div>
          <h2 id="crew-title">{crew.title}</h2>
          <p className="quiet">{crew.intro}</p>
        </div>
        {members && members.length > 0 ? <Tally members={current} /> : null}
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
        <div
          ref={orgRef}
          className={`org ${columns ? "org-columns" : "org-list"}`}
          style={{ "--n": Math.max(1, columnCount) } as CSSProperties}
          aria-label={crew.orgLabel}
          role="group"
        >
          <div className={`org-top${sideBeside && tree.others.length > 0 ? " has-side" : ""}`}>
            <div className="org-spine">
              <div className="org-chairman">
                <Avatar name={chairman} kind="person" size="md" />
                <span>
                  <span className="crew-card-name">{chairman}</span>
                  <span className="crew-card-role">
                    {crew.chairman} · {crew.you}
                  </span>
                </span>
              </div>
              {tree.ceo ? (
                <>
                  <span className="org-line" aria-hidden="true" />
                  <ul className="plain org-ceo">{card(tree.ceo, { featured: true })}</ul>
                </>
              ) : null}
            </div>
            {sideBeside && tree.others.length > 0 ? (
              <section className="org-side" aria-labelledby="crew-side">
                <h3 id="crew-side" className="org-side-head">
                  {crew.side}
                  <span className="quiet">{crew.sideHint}</span>
                </h3>
                <ul className="plain org-side-list">{tree.others.map((member) => card(member))}</ul>
              </section>
            ) : null}
          </div>

          {columnCount > 0 ? (
            <div className="org-teams">
              <span className="org-bus" aria-hidden="true" />
              {tree.teams.map((team) => {
                const size = team.members.length + (team.lead ? 1 : 0);
                return (
                  <section key={team.name} className="org-team" aria-labelledby={`crew-team-${team.name}`}>
                    <h3 id={`crew-team-${team.name}`} className="org-team-head">
                      <span>{crew.teamLabel(team.name)}</span>
                      <span className="quiet tabular">{crew.teamCount(size)}</span>
                    </h3>
                    <ul className="plain org-team-list">
                      {team.lead ? card(team.lead, { showLead: size > 1 }) : null}
                      {team.members.map((member) => card(member))}
                    </ul>
                  </section>
                );
              })}
              {sideColumn ? (
                <section className="org-team org-team-side" aria-labelledby="crew-side">
                  <h3 id="crew-side" className="org-team-head">
                    <span>{crew.side}</span>
                    <span className="quiet">{crew.sideHint}</span>
                  </h3>
                  <ul className="plain org-team-list">{tree.others.map((member) => card(member))}</ul>
                </section>
              ) : null}
            </div>
          ) : null}

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
          canRename={canRename}
          onRenamed={() => {
            data.reload();
            onRenamed?.();
          }}
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
