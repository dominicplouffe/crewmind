/** The pill tone for each crew status, matching the avatar dots. The word always carries the meaning. */
import type { Tone } from "../ui/Status";
import type { CrewStatus } from "./logic";

export const STATUS_TONE: Record<CrewStatus, Tone> = { working: "success", waiting: "warning", blocked: "danger", idle: "neutral" };
