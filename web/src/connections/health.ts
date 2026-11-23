/** A connection's health at a glance: a tone and a word (CON-15). Tone is never the only signal. */
import type { Tone } from "../ui/Status";
import { connectionWords as words } from "../strings.connections";

export interface Health {
  tone: Tone;
  label: string;
}

interface Item {
  state: string;
  expires_on?: string | null;
  expires_soon?: boolean;
  last_used_at?: string | null;
  used_in: number;
  mcp?: { state: string } | null;
}

const DAY = 86_400_000;

export function daysUntil(day: string, now: number): number {
  const end = Date.parse(`${day}T23:59:59Z`);
  return Math.max(0, Math.ceil((end - now) / DAY) - 1);
}

export function healthOf(item: Item, now: number = Date.now()): Health {
  if (item.state === "expired") return { tone: "danger", label: words.health.expired };
  if (item.mcp && item.mcp.state !== "active") {
    const tone = item.mcp.state === "needs sign-in" ? "warning" : "danger";
    return { tone, label: words.mcp.states[item.mcp.state] ?? item.mcp.state };
  }
  // The server says when an expiry is near, by the install's own reminder setting.
  if (item.expires_on && item.expires_soon) {
    const days = daysUntil(item.expires_on, now);
    return { tone: "warning", label: days === 0 ? words.health.expiresToday : words.health.expiresIn(days) };
  }
  if (item.used_in === 0) return { tone: "neutral", label: words.health.notInUse };
  if (!item.last_used_at) return { tone: "neutral", label: words.health.neverUsed };
  return { tone: "success", label: words.health.working };
}

/** The line under a name that says how it is used, in plain words. */
export function usageLine(item: {
  kind: string;
  mcp?: { url?: string | null; tools: { permission: string; gone: boolean }[] } | null;
  delivery?: string | null;
  sites?: string[];
  env_name?: string | null;
  shape?: string | null;
}): string {
  if (item.kind === "variable") return words.variableAs(item.env_name ?? "");
  if (item.kind === "mcp_server") {
    const tools = (item.mcp?.tools ?? []).filter((tool) => !tool.gone);
    const allowed = tools.filter((tool) => tool.permission === "allowed").length;
    return [item.mcp?.url ?? "", words.mcp.toolsSummary(allowed, tools.length)].filter(Boolean).join(" · ");
  }
  if (item.delivery === "given") return words.givenAs(item.env_name ?? "", item.shape === "file");
  return words.sentTo(item.sites ?? []);
}
