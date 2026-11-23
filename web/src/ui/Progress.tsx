/**
 * Progress through the plan as one bar: done, in progress, accepted and not started, and proposed.
 * Each segment is labelled in text beside the bar, so colour is never the only cue.
 */
export interface Segment {
  key: string;
  label: string;
  value: number;
  tone: "done" | "active" | "todo" | "proposed";
}

export function SegmentBar({ segments, label }: { segments: Segment[]; label: string }): JSX.Element {
  const total = segments.reduce((sum, segment) => sum + segment.value, 0);
  const text = segments.map((segment) => `${segment.value} ${segment.label}`).join(", ");
  return (
    <div className="segbar" role="img" aria-label={`${label}: ${text}`}>
      {total === 0 ? <span className="segbar-empty" /> : null}
      {segments
        .filter((segment) => segment.value > 0)
        .map((segment) => (
          <span
            key={segment.key}
            className={`segbar-part seg-${segment.tone}`}
            style={{ flexGrow: segment.value }}
          />
        ))}
    </div>
  );
}

export function Meter({ value, max, label, tone = "accent" }: { value: number; max: number; label: string; tone?: "accent" | "warning" | "danger" }): JSX.Element {
  const share = max <= 0 ? 0 : Math.min(1, Math.max(0, value / max));
  return (
    <div
      className={`meter meter-${tone}`}
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={value}
    >
      <span style={{ width: `${share * 100}%` }} />
    </div>
  );
}
