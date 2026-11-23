/** The person's projects, loaded once for the shell and shared with the pages that list them. */
import { createContext, useContext, type ReactNode } from "react";
import { get, type Project } from "../api/client";
import { useLoad, type Loaded } from "../lib/useLoad";

const ProjectsContext = createContext<Loaded<{ items: Project[] }> | null>(null);

export function ProjectsProvider({ children }: { children: ReactNode }): JSX.Element {
  const projects = useLoad(() => get("/v1/projects/list", {}), []);
  return <ProjectsContext.Provider value={projects}>{children}</ProjectsContext.Provider>;
}

export function useProjects(): Loaded<{ items: Project[] }> {
  const value = useContext(ProjectsContext);
  if (!value) throw new Error("useProjects needs a ProjectsProvider");
  return value;
}

/** Projects that are under way, first; then the rest. Newest first within each. */
export const LIVE_STATES = ["running", "held", "paused", "ready"];

export function sortProjects(items: readonly Project[]): Project[] {
  return [...items].sort((left, right) => {
    const a = LIVE_STATES.includes(left.state) ? 0 : 1;
    const b = LIVE_STATES.includes(right.state) ? 0 : 1;
    if (a !== b) return a - b;
    return right.created_at.localeCompare(left.created_at);
  });
}
