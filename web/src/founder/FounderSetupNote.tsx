/**
 * Says what is missing when the Founder has no model (LLM-14, FND-2), and offers the fix where
 * the person is: an admin sets up a model and tries again; a member is told to ask an admin and
 * can fill in a form instead. Shown before a brief is written, and in place of "send your
 * message again" when a turn failed for this reason.
 */
import { Link } from "react-router-dom";
import { RotateCcw, Sparkles } from "lucide-react";
import { orList, useAdminNames } from "../onboarding/useAdminNames";
import { useSetupStatus } from "../onboarding/useSetupStatus";
import { settingsPath } from "../settings/paths";
import { settingsWords } from "../strings.settings";

/** The server's words when the Founder has no model to run on (gateway `founder_call`). */
const NO_MODEL = [/no model is set for the founder/i, /has no model the founder can use/i];

export function isNoModelFailure(failure: string | null | undefined): boolean {
  return Boolean(failure) && NO_MODEL.some((pattern) => pattern.test(failure ?? ""));
}

/** What the person last said in the conversation, to send again when retrying. */
export function lastSaid(lines: { author: string; body: string }[]): string | null {
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    const line = lines[index];
    if (line?.author === "person" && line.body.trim()) return line.body;
  }
  return null;
}

interface Props {
  /** "before": shown above an empty brief; "failed": a Founder turn failed for want of a model. */
  when: "before" | "failed";
  /** Where to come back to after setup, such as the drafting conversation. */
  returnTo?: string;
  /** Sends the conversation on again (failed only). */
  onRetry?(): void;
  retrying?: boolean;
}

export function FounderSetupNote({ when, returnTo, onRetry, retrying = false }: Props): JSX.Element {
  const words = settingsWords.setupNote;
  const status = useSetupStatus();
  const admins = useAdminNames(!status.isAdmin && !status.loading);
  const failed = when === "failed";
  const fixed = failed && status.isAdmin && !status.loading && status.founderReady;
  const setupLink = status.hasModelKey
    ? settingsPath("founder", returnTo)
    : `/welcome${returnTo ? `?next=${encodeURIComponent(returnTo)}` : ""}`;

  const retry = onRetry ? (
    <button type="button" className={fixed ? "button primary" : "button"} onClick={onRetry} disabled={retrying}>
      <RotateCcw size={16} aria-hidden="true" />
      {retrying ? words.trying : words.tryAgain}
    </button>
  ) : null;

  if (status.isAdmin) {
    return (
      <div className={fixed ? "note note-success setup-note" : "note note-warning setup-note"} role={failed ? "alert" : "status"} data-testid="founder-setup-note">
        <p className="note-title">{fixed ? words.fixedTitle : failed ? words.adminFailedTitle : words.adminTitle}</p>
        {fixed ? null : <p className="note-hint">{failed ? words.adminFailedBody : words.adminBody}</p>}
        <div className="note-actions">
          {fixed ? null : (
            <Link to={setupLink} className="button primary">
              <Sparkles size={16} aria-hidden="true" />
              {words.setUp}
            </Link>
          )}
          {fixed ? retry : null}
        </div>
      </div>
    );
  }

  return (
    <div className="note note-warning setup-note" role={failed ? "alert" : "status"} data-testid="founder-setup-note">
      <p className="note-title">{failed ? words.memberFailedTitle : words.memberTitle}</p>
      <p className="note-hint">{admins.length > 0 ? words.askAdminNamed(orList(admins)) : words.askAdmin}</p>
      {failed ? null : <p className="note-hint">{words.memberBody}</p>}
      <div className="note-actions">
        <Link to="/projects?new=form" className="button primary">
          {words.byForm}
        </Link>
        {retry}
      </div>
    </div>
  );
}
