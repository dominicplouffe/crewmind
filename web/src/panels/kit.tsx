/**
 * Small display pieces the panels share: an empty state with an icon and a next step, and a loading
 * placeholder shaped like a list. Presentation only.
 */
import type { LucideIcon } from "lucide-react";
import { Inbox } from "lucide-react";
import type { ReactNode } from "react";
import { t } from "../strings";
import { Skeleton } from "../ui/Skeleton";

interface EmptyProps {
  title: string;
  next: string;
  icon?: LucideIcon;
  /** A button or link for the next step. */
  action?: ReactNode;
}

export function Empty({ title, next, icon: Icon = Inbox, action }: EmptyProps): JSX.Element {
  return (
    <div className="empty">
      <span className="empty-icon" aria-hidden="true">
        <Icon size={22} strokeWidth={1.75} />
      </span>
      <p className="empty-title">{title}</p>
      <p className="quiet">{next}</p>
      {action ? <div className="empty-action">{action}</div> : null}
    </div>
  );
}

/** A loading placeholder shaped like a few rows. */
export function Loading({ label = t.common.loading, lines = 3 }: { label?: string; lines?: number }): JSX.Element {
  return (
    <div className="panel-loading">
      <Skeleton lines={lines} label={label} />
    </div>
  );
}
