/**
 * The company made visible: the chairman, the CEO with any side seats beside it, and the teams side
 * by side, each with its members (CHAT-12, CHAT-18, EXE-4). Each agent is a card with what it is
 * doing now (from its runs and the tasks it holds) and its share of the squad's tokens; a card opens
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
import { squad } from "../strings.squad";
import { Avatar } from "../ui/Avatar";
import { Meter } from "../ui/Progress";
import { Skeleton } from "../ui/Skeleton";
import { AgentSheet } from "./AgentSheet";
import { useSquad } from "./data";
import { SUMMARY_ORDER, orgTree, statusCounts, tokenShare, type SquadMember } from "./logic";
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
  member: SquadMember;
  all: readonly SquadMember[];
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
      ? squad.activeNow
      : member.status === "idle"
        ? squad.runs(member.runs)
        : member.lastActive
          ? squad.lastActive(fromNow(member.lastActive))
          : squad.neverActive;
  return (
    <button
      type="button"
      className={`squad-card status-${member.status}${featured ? " featured" : ""}${fresh ? " is-new" : ""}`}
      style={fresh ? ({ "--i": order } as CSSProperties) : undefined}
      onClick={onOpen}
      data-testid="squad-card"
      data-status={member.status}
    >
      <span className="squad-card-top">
        <StatusFace seat={member.name} status={member.status} size={featured ? "lg" : "md"} />
        <span className="squad-card-who">
          <span className="squad-card-name">
            {member.displayName}
            {showLead ? <span className="badge">{squad.lead}</span> : null}
          </span>
          {member.roleLabel.trim().toLowerCase() !== member.displayName.trim().toLowerCase() ? (
            <span className="squad-card-role" title={member.role}>
              {member.roleLabel}
            </span>
          ) : null}
        </span>
      </span>
      <span className="squad-card-now">
        {member.now}
        {member.doing ? <span className="squad-card-doing"> · {member.doing}</span> : null}
      </span>
      {member.reason ? (
        <span className="squad-card-reason">
          <span className="visually-hidden">{squad.reason}: </span>
          <AgentText text={member.reason} />
        </span>
      ) : null}
      <span className="squad-card-foot">
        <Meter value={Math.round(part * 1000)} max={1000} label={squad.shareLabel(member.displayName, shareText)} />
        <span className="squad-card-meta tabular">
          <span>{squad.share(tokens(member.tokens), shareText)}</span>
          <span>{when}</span>
        </span>
      </span>
    </button>
  );
}

function SquadSkeleton(): JSX.Element {
  return (
    <div className="org org-columns" aria-busy="true" style={{ "--n": 3 } as CSSProperties}>
      <Skeleton lines={1} label={squad.loading} />
      <div className="org-teams">
        {[0, 1, 2].map((index) => (
          <div key={index} className="org-team" aria-hidden="true">
            <div className="squad-card skeleton-card">
              <span className="skeleton squad-skel-avatar" />
              <span className="skeleton line" />
              <span className="skeleton line" style={{ width: "60%" }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Tally({ members }: { members: SquadMember[] }): JSX.Element {
  const counts = statusCounts(members);
  const entries = SUMMARY_ORDER.map((status) => ({ status, count: counts[status] })).filter((entry) => entry.count > 0);
  return (
    <>
      <ul className="plain squad-tally" aria-label={squad.summaryLabel}>
        {entries.map((entry) => (
          <li key={entry.status} className="tabular">
            <span className={`squad-dot-inline dot-${entry.status}`} aria-hidden="true" />
            {squad.summary([entry])}
          </li>
        ))}
      </ul>
      <p className="visually-hidden" aria-live="polite">
        {squad.summary(entries)}
      </p>
    </>
  );
}

export function SquadView({ projectId, changes, header, canRename, onMessage, onOpenRun, onRenamed }: Props): JSX.Element {
  const { person } = useAuth();
  const data = useSquad(projectId, changes, header);
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
  const card = (member: SquadMember, options: { featured?: boolean; showLead?: boolean } = {}): JSX.Element => {
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
  const chairman = person?.name ?? squad.you;

  return (
    <section className="squad" aria-labelledby="squad-title" data-testid="squad-view">
      <header className="squad-head">
        <div>
          <h2 id="squad-title">{squad.title}</h2>
          <p className="quiet">{squad.intro}</p>
        </div>
        {members && members.length > 0 ? <Tally members={current} /> : null}
      </header>

      {data.error && !members ? (
        <div className="stack">
          <ErrorNote error={data.error} />
          <div>
            <button type="button" className="button small" onClick={data.reload}>
              {squad.retry}
            </button>
          </div>
        </div>
      ) : null}
      {!members && !data.error ? <SquadSkeleton /> : null}

      {tree && members && members.length === 0 ? (
        <div className="empty squad-empty">
          <span className="empty-icon">
            <Users size={22} aria-hidden="true" />
          </span>
          <p className="empty-title">{squad.emptyTitle}</p>
          <p className="quiet">{squad.emptyNext}</p>
        </div>
      ) : null}

      {tree && members && members.length > 0 ? (
        <div
          ref={orgRef}
          className={`org ${columns ? "org-columns" : "org-list"}`}
          style={{ "--n": Math.max(1, columnCount) } as CSSProperties}
          aria-label={squad.orgLabel}
          role="group"
        >
          <div className={`org-top${sideBeside && tree.others.length > 0 ? " has-side" : ""}`}>
            <div className="org-spine">
              <div className="org-chairman">
                <Avatar name={chairman} kind="person" size="md" />
                <span>
                  <span className="squad-card-name">{chairman}</span>
                  <span className="squad-card-role">
                    {squad.chairman} · {squad.you}
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
              <section className="org-side" aria-labelledby="squad-side">
                <h3 id="squad-side" className="org-side-head">
                  {squad.side}
                  <span className="quiet">{squad.sideHint}</span>
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
                  <section key={team.name} className="org-team" aria-labelledby={`squad-team-${team.name}`}>
                    <h3 id={`squad-team-${team.name}`} className="org-team-head">
                      <span>{squad.teamLabel(team.name)}</span>
                      <span className="quiet tabular">{squad.teamCount(size)}</span>
                    </h3>
                    <ul className="plain org-team-list">
                      {team.lead ? card(team.lead, { showLead: size > 1 }) : null}
                      {team.members.map((member) => card(member))}
                    </ul>
                  </section>
                );
              })}
              {sideColumn ? (
                <section className="org-team org-team-side" aria-labelledby="squad-side">
                  <h3 id="squad-side" className="org-team-head">
                    <span>{squad.side}</span>
                    <span className="quiet">{squad.sideHint}</span>
                  </h3>
                  <ul className="plain org-team-list">{tree.others.map((member) => card(member))}</ul>
                </section>
              ) : null}
            </div>
          ) : null}

          {tree.former.length > 0 ? (
            <details className="squad-former">
              <summary>{squad.former(tree.former.length)}</summary>
              <ul className="plain squad-grid">{tree.former.map((member) => card(member))}</ul>
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
