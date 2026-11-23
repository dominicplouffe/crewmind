/** Pieces the crew views share: an avatar with its status dot. Presentation only. */
import { Avatar } from "../ui/Avatar";
import type { CrewStatus } from "./logic";

/**
 * An agent's avatar with a dot for its status. The dot is decoration: the status is always given in
 * words beside it (WCAG 1.4.1). Drawn here rather than on the avatar so every crew status has a dot.
 */
export function StatusFace({
  name,
  status,
  size = "md",
}: {
  name: string;
  status: CrewStatus | null;
  size?: "xs" | "sm" | "md" | "lg" | "xl";
}): JSX.Element {
  return (
    <span className={`crew-face crew-face-${size}`} aria-hidden="true">
      <Avatar name={name} size={size} />
      {status ? <span className={`crew-dot dot-${status}`} /> : null}
    </span>
  );
}
