/** Pieces the squad views share: an avatar with its status dot. Presentation only. */
import type { SquadStatus } from "./logic";
import { AgentAvatar } from "./names";

/**
 * An agent's avatar with a dot for its status. The dot is decoration: the status is always given in
 * words beside it (WCAG 1.4.1). Drawn here rather than on the avatar so every squad status has a dot.
 */
export function StatusFace({
  seat,
  status,
  size = "md",
}: {
  /** The agent's seat name; the avatar shows the name it goes by. */
  seat: string;
  status: SquadStatus | null;
  size?: "xs" | "sm" | "md" | "lg" | "xl";
}): JSX.Element {
  return (
    <span className={`squad-face squad-face-${size}`} aria-hidden="true">
      <AgentAvatar seat={seat} size={size} />
      {status ? <span className={`squad-dot dot-${status}`} /> : null}
    </span>
  );
}
