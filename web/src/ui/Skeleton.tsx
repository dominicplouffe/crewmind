/** Loading placeholders shaped like what is coming, so the page does not jump when it arrives. */
import { t } from "../strings";

export function Skeleton({ lines = 3, block = false, label = t.common.loading }: { lines?: number; block?: boolean; label?: string }): JSX.Element {
  return (
    <div role="status" aria-live="polite" className="skeleton-group">
      <span className="visually-hidden">{label}</span>
      {block ? <span className="skeleton block" aria-hidden="true" /> : null}
      {Array.from({ length: lines }, (_, index) => (
        <span key={index} className="skeleton line" aria-hidden="true" style={{ width: `${92 - ((index * 17) % 40)}%` }} />
      ))}
    </div>
  );
}
