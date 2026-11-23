/**
 * Sorting and grouping files for the deliverables gallery (ART-3, CHAT-16). Display only: the
 * kind, status and author come from the server as given.
 */
import type { Artifact } from "../api/client";
import { extensionOf, previewKind } from "../lib/files";

export type Category = "documents" | "code" | "images" | "data" | "other";
export type Filter = "all" | Category;
export type Sort = "recent" | "name" | "status";
export type Scope = "delivered" | "everything";

export const FILTERS: Filter[] = ["all", "documents", "code", "images", "data", "other"];
export const SORTS: Sort[] = ["recent", "name", "status"];

const DATA_EXTENSIONS = new Set(["csv", "tsv", "json", "ndjson", "jsonl", "xlsx", "xls", "ods", "parquet", "sqlite", "db"]);
const DELIVERED_KINDS = new Set(["deliverable", "report", "upload"]);
/** Further along first. Unknown labels sort last. */
const STATUS_ORDER = ["delivered", "verified", "in review", "draft"];

export function categoryOf(item: Pick<Artifact, "name" | "media_type">): Category {
  const kind = previewKind(item.name, item.media_type);
  if (DATA_EXTENSIONS.has(extensionOf(item.name)) || kind === "csv") return "data";
  if (kind === "image") return "images";
  if (kind === "code") return "code";
  if (kind === "markdown" || kind === "text" || kind === "pdf" || kind === "html") return "documents";
  return "other";
}

/** Deliverables, reports and uploads, unless the person asks for working files as well. */
export function inScope(item: Artifact, scope: Scope): boolean {
  if (scope === "everything") return true;
  return DELIVERED_KINDS.has(item.kind) && !item.superseded_by;
}

/** The scope to start in: deliverables when there are any, otherwise everything so the page is not empty. */
export function defaultScope(items: readonly Artifact[]): Scope {
  return items.some((item) => inScope(item, "delivered")) ? "delivered" : "everything";
}

function statusRank(status: string): number {
  const rank = STATUS_ORDER.indexOf(status);
  return rank === -1 ? STATUS_ORDER.length : rank;
}

export function arrange(items: readonly Artifact[], filter: Filter, sort: Sort, scope: Scope): Artifact[] {
  const shown = items.filter((item) => inScope(item, scope) && (filter === "all" || categoryOf(item) === filter));
  const byRecent = (a: Artifact, b: Artifact): number => Date.parse(b.last_change) - Date.parse(a.last_change);
  const byName = (a: Artifact, b: Artifact): number => a.name.localeCompare(b.name, undefined, { numeric: true });
  return shown.sort((a, b) => {
    if (sort === "name") return byName(a, b);
    if (sort === "status") return statusRank(a.status) - statusRank(b.status) || byRecent(a, b);
    return byRecent(a, b) || byName(a, b);
  });
}

export function countByFilter(items: readonly Artifact[], scope: Scope): Record<Filter, number> {
  const counts: Record<Filter, number> = { all: 0, documents: 0, code: 0, images: 0, data: 0, other: 0 };
  for (const item of items) {
    if (!inScope(item, scope)) continue;
    counts.all += 1;
    counts[categoryOf(item)] += 1;
  }
  return counts;
}

export type AuthorKind = "agent" | "person" | "platform";

/** Who made a file: an agent of the crew, a person (uploads), or the platform (reports). */
export function authorKind(item: Pick<Artifact, "kind" | "last_author">, seats: ReadonlySet<string>): AuthorKind {
  if (seats.has(item.last_author)) return "agent";
  if (item.last_author === "platform" || item.last_author === "crewmind") return "platform";
  if (item.kind === "upload") return "person";
  return item.kind === "report" ? "platform" : "person";
}

/** The first lines of a text file, for a card. */
export function excerptLines(text: string, lines: number, width = 120): string {
  return text
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .slice(0, lines)
    .map((line) => (line.length > width ? `${line.slice(0, width)}…` : line))
    .join("\n");
}

/** The opening of a markdown file, cut at a paragraph break near `chars` so no block is left open. */
export function markdownExcerpt(text: string, chars: number): string {
  const source = text.replace(/\r\n?/g, "\n").replace(/^---\n[\s\S]*?\n---\n/, "");
  if (source.length <= chars) return source;
  const cut = source.lastIndexOf("\n\n", chars);
  let excerpt = source.slice(0, cut > chars / 3 ? cut : chars);
  // Close a code fence the cut left open.
  if ((excerpt.match(/^```/gm) ?? []).length % 2 === 1) excerpt += "\n```";
  return excerpt;
}
