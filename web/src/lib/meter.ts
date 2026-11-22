/** A size meter: how full something is against its cap, and by how much it is over. */

export interface Meter {
  /** 0 to 100, for a progress bar. */
  percent: number;
  over: boolean;
  /** How far past the cap; 0 when within it. */
  overBy: number;
}

export function meter(used: number, cap: number): Meter {
  const overBy = Math.max(0, used - cap);
  const percent = cap <= 0 ? (used > 0 ? 100 : 0) : Math.max(0, Math.min(100, Math.round((used / cap) * 100)));
  return { percent, over: overBy > 0, overBy };
}
