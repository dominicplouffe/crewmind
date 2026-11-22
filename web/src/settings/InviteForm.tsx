/**
 * Invites a person (ACC-2): name, email and role. The server answers with a one-time link, shown
 * with a Copy button, because crewmind sends no email itself.
 */
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { post, type Schemas } from "../api/client";
import { ErrorNote } from "../components/common";
import { formatDateTime } from "../lib/format";
import { settingsWords } from "../strings.settings";
import { ChoiceCard } from "./ChoiceCard";
import { CopyLink } from "./CopyLink";

type Role = Schemas["InstanceRole"];
type Link = Schemas["LinkOutput"];

export interface Invited {
  name: string;
  email: string;
  role: Role;
  link: Link;
}

interface Props {
  onInvited(invited: Invited): void;
  autoFocus?: boolean;
}

const ROLES: Role[] = ["member", "admin"];

export function InviteForm({ onInvited, autoFocus = false }: Props): JSX.Element {
  const words = settingsWords.people;
  const id = useId();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("member");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [invited, setInvited] = useState<Invited | null>(null);
  const linkHeading = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    if (invited) linkHeading.current?.focus();
  }, [invited]);

  const submit = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const link = await post("/v1/people/invite", { name: name.trim(), email: email.trim(), role });
      const result = { name: name.trim(), email: email.trim(), role, link };
      setInvited(result);
      onInvited(result);
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  };

  const again = (): void => {
    setInvited(null);
    setName("");
    setEmail("");
    setRole("member");
    window.setTimeout(() => document.getElementById(`${id}-name`)?.focus(), 0);
  };

  if (invited) {
    return (
      <div className="invite-link note note-success">
        <p className="note-title" tabIndex={-1} ref={linkHeading}>
          {words.linkTitle(invited.name)}
        </p>
        <p className="note-hint">{words.linkBody(formatDateTime(invited.link.expires_at))}</p>
        <CopyLink link={invited.link.link} label={words.linkLabel(invited.name)} />
        <div className="note-actions">
          <button type="button" className="button" onClick={again}>
            {words.invite}
          </button>
        </div>
      </div>
    );
  }

  return (
    <form className="invite-form" onSubmit={(event) => void submit(event)}>
      <div className="invite-fields">
        <div className="field">
          <label htmlFor={`${id}-name`}>{words.inviteName}</label>
          <input id={`${id}-name`} autoComplete="off" required value={name} autoFocus={autoFocus} onChange={(event) => setName(event.target.value)} />
        </div>
        <div className="field">
          <label htmlFor={`${id}-email`}>{words.inviteEmail}</label>
          <input
            id={`${id}-email`}
            type="email"
            autoComplete="off"
            spellCheck={false}
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>
      </div>
      <fieldset className="choice-cards compact">
        <legend>{words.inviteRole}</legend>
        {ROLES.map((value) => (
          <ChoiceCard
            key={value}
            name={`${id}-role`}
            value={value}
            checked={role === value}
            onChange={() => setRole(value)}
            title={words.role[value] ?? value}
            help={words.roleHelp[value]}
          />
        ))}
      </fieldset>
      <ErrorNote error={error} />
      <button type="submit" className="button primary" disabled={busy || !name.trim() || !email.trim()}>
        {busy ? words.inviting : words.inviteSubmit}
      </button>
    </form>
  );
}
