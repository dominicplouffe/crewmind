/** The pill tone for each squad status, matching the status dots. The word always carries the meaning. */
import type { Tone } from "../ui/Status";
import type { SquadStatus } from "./logic";

export const STATUS_TONE: Record<SquadStatus, Tone> = {
  working: "success",
  holding: "accent",
  review: "info",
  waiting: "warning",
  blocked: "danger",
  idle: "neutral",
};
