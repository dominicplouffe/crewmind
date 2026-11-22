/** Loads the roster and runs for the crew views. Display only; the server decides every state. */
import { useMemo } from "react";
import { get, type Header } from "../api/client";
import { useLoad } from "../lib/useLoad";
import { crewMembers, type CrewMember, type Run } from "./logic";

const PAGE = 200;
/** Stop paging after this many runs; the oldest beyond it only change the totals slightly. */
const MAX_RUNS = 4000;

/** Every run of the project, oldest first (the server pages forward). */
export async function loadRuns(projectId: string, since?: string): Promise<Run[]> {
  const items: Run[] = [];
  let after: string | undefined;
  for (;;) {
    const page = await get("/v1/runs/list", { project_id: projectId, after, limit: PAGE, since });
    items.push(...page.items);
    if (!page.next || items.length >= MAX_RUNS) return items;
    after = page.next;
  }
}

export interface CrewData {
  members: CrewMember[] | undefined;
  runs: Run[];
  teams: string[];
  error: unknown;
  reload(): void;
}

/**
 * The crew with live status: reloads whenever the project changes. `recentHours` loads only recent
 * runs, enough for status in a compact view; totals then cover that window only.
 */
export function useCrew(projectId: string, changes: number, header: Header | null, recentHours?: number): CrewData {
  const roster = useLoad(() => get("/v1/roster/show", { project_id: projectId }), [projectId, changes]);
  const runs = useLoad(
    () => loadRuns(projectId, recentHours ? new Date(Date.now() - recentHours * 3_600_000).toISOString() : undefined),
    [projectId, changes, recentHours],
  );
  const members = useMemo(
    () => (roster.data && runs.data ? crewMembers(roster.data, header, runs.data) : undefined),
    [roster.data, runs.data, header],
  );
  return {
    members,
    runs: runs.data ?? [],
    teams: roster.data?.teams ?? [],
    error: roster.error ?? runs.error,
    reload: () => {
      roster.reload();
      runs.reload();
    },
  };
}
