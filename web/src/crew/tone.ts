/** The pill tone for each crew status, matching the status dots. The word always carries the meaning. */
import type { Tone } from "../ui/Status";
import type { CrewStatus } from "./logic";

export const STATUS_TONE: Record<CrewStatus, Tone> = {
  working: "success",
  holding: "accent",
  review: "info",
  waiting: "warning",
  blocked: "danger",
  idle: "neutral",
};
