/**
 * People on the install (ACC-2, ACC-3): who they are, their role and state, and the admin's
 * actions on each: change role, issue a new sign-in link, deactivate or reactivate. Invites
 * produce a one-time link to hand over.
 */
import { useState } from "react";
import { MoreHorizontal, UserPlus, Users } from "lucide-react";
import { get, post, type Schemas } from "../api/client";
import { useAuth } from "../auth";
import { ErrorNote } from "../components/common";
import { formatDateTime } from "../lib/format";
import { useLoad } from "../lib/useLoad";
import { settingsWords } from "../strings.settings";
import { Avatar } from "../ui/Avatar";
import { Menu, type MenuItem } from "../ui/Menu";
import { Skeleton } from "../ui/Skeleton";
import { Pill } from "../ui/Status";
import { CopyLink } from "./CopyLink";
import { InviteForm } from "./InviteForm";

type Person = Schemas["PersonItem"];
type LinkOutput = Schemas["LinkOutput"];

function PersonRow({ person, self, onChanged }: { person: Person; self: boolean; onChanged(next: Person): void }): JSX.Element {
  const words = settingsWords.people;
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [link, setLink] = useState<LinkOutput | null>(null);

  const run = (work: () => Promise<Person | null>): void => {
    setBusy(true);
    setError(null);
    work()
      .then((next) => {
        if (next) onChanged(next);
      })
      .catch((reason: unknown) => setError(reason))
      .finally(() => setBusy(false));
  };

  const ref = { person_id: person.person_id };
  const items: MenuItem[] = [];
  if (person.state !== "deactivated") {
    items.push(
      person.role === "admin"
        ? { key: "member", label: words.makeMember, run: () => run(() => post("/v1/people/set_role", { ...ref, role: "member" })) }
        : { key: "admin", label: words.makeAdmin, run: () => run(() => post("/v1/people/set_role", { ...ref, role: "admin" })) },
      {
        key: "link",
        label: words.newLink,
        run: () =>
          run(async () => {
            setLink(await post("/v1/people/reset_link", ref));
            return null;
          }),
      },
      { key: "deactivate", label: words.deactivate, danger: true, run: () => setConfirming(true) },
    );
  } else {
    items.push({ key: "reactivate", label: words.reactivate, run: () => run(() => post("/v1/people/reactivate", ref)) });
  }

  return (
    <li className={person.state === "deactivated" ? "person-row inactive" : "person-row"} data-testid="person">
      <div className="person-main">
        <Avatar name={person.name} kind="person" size="md" />
        <div className="person-text">
          <p className="person-name">
            <span>{person.name}</span>
            {self ? <Pill tone="accent" dot={false}>{words.you}</Pill> : null}
          </p>
          <p className="quiet person-email">{person.email}</p>
        </div>
        <div className="person-tags">
          <Pill tone={person.role === "admin" ? "accent" : "neutral"} dot={false}>
            {words.role[person.role] ?? person.role}
          </Pill>
          {person.state !== "active" ? (
            <Pill tone={person.state === "invited" ? "info" : "neutral"}>{words.state[person.state] ?? person.state}</Pill>
          ) : null}
        </div>
        {self ? (
          <span className="person-menu-spacer" aria-hidden="true" />
        ) : (
          <Menu
            label={words.actions(person.name)}
            className="button ghost icon-only"
            button={<MoreHorizontal size={18} aria-hidden="true" />}
            items={items}
          />
        )}
      </div>
      {busy ? <p className="quiet" role="status">{settingsWords.common.saving}</p> : null}
      <ErrorNote error={error} />
      {confirming ? (
        <div className="note note-warning person-confirm" role="group" aria-label={words.deactivate}>
          <p className="note-title">{words.deactivateConfirm(person.name)}</p>
          <div className="note-actions">
            <button
              type="button"
              className="button danger"
              disabled={busy}
              onClick={() => {
                setConfirming(false);
                run(() => post("/v1/people/deactivate", ref));
              }}
            >
              {words.deactivateYes}
            </button>
            <button type="button" className="button" onClick={() => setConfirming(false)} autoFocus>
              {settingsWords.common.cancel}
            </button>
          </div>
        </div>
      ) : null}
      {link ? (
        <div className="note person-link">
          <p className="note-title">{words.linkTitle(person.name)}</p>
          <p className="note-hint">{words.linkBody(formatDateTime(link.expires_at))}</p>
          <CopyLink link={link.link} label={words.linkLabel(person.name)} />
          <div className="note-actions">
            <button type="button" className="button small" onClick={() => setLink(null)}>
              {words.done}
            </button>
          </div>
        </div>
      ) : null}
    </li>
  );
}

export function PeopleSection(): JSX.Element {
  const words = settingsWords.people;
  const { person: me } = useAuth();
  const [extra, setExtra] = useState<Person[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [moreError, setMoreError] = useState<unknown>(null);
  const first = useLoad(async () => {
    const page = await get("/v1/people/list", {});
    setExtra([]);
    setNext(page.next ?? null);
    return page.items;
  }, []);
  const people = [...(first.data ?? []), ...extra];
  const others = people.filter((person) => person.person_id !== me?.person_id);

  const replace = (changed: Person): void => {
    if (first.data?.some((person) => person.person_id === changed.person_id)) {
      first.setData(first.data.map((person) => (person.person_id === changed.person_id ? changed : person)));
    } else {
      setExtra((current) => current.map((person) => (person.person_id === changed.person_id ? changed : person)));
    }
  };

  const more = (): void => {
    if (!next) return;
    setMoreError(null);
    get("/v1/people/list", { after: next })
      .then((page) => {
        setExtra((current) => [...current, ...page.items]);
        setNext(page.next ?? null);
      })
      .catch((reason: unknown) => setMoreError(reason));
  };

  return (
    <>
      <section className="card settings-card" aria-labelledby="people-title">
        <div className="settings-card-head">
          <h3 id="people-title">{words.listTitle}</h3>
          <p className="quiet">{words.intro}</p>
        </div>
        {first.error ? (
          <div className="stack">
            <ErrorNote error={first.error} />
            <div>
              <button type="button" className="button small" onClick={first.reload}>
                {settingsWords.common.retry}
              </button>
            </div>
          </div>
        ) : null}
        {first.loading && !first.data ? <Skeleton lines={3} block /> : null}
        {first.data ? (
          <ul className="person-list plain" aria-label={words.listTitle}>
            {people.map((person) => (
              <PersonRow key={person.person_id} person={person} self={person.person_id === me?.person_id} onChanged={replace} />
            ))}
          </ul>
        ) : null}
        {first.data && others.length === 0 ? (
          <div className="empty compact">
            <span className="empty-icon" aria-hidden="true">
              <Users size={20} />
            </span>
            <p className="empty-title">{words.emptyTitle}</p>
            <p className="quiet">{words.emptyBody}</p>
          </div>
        ) : null}
        <ErrorNote error={moreError} />
        {next ? (
          <button type="button" className="button" onClick={more}>
            {words.more}
          </button>
        ) : null}
      </section>
      <section className="card settings-card" aria-labelledby="invite-title">
        <div className="settings-card-head">
          <h3 id="invite-title">
            <UserPlus size={18} aria-hidden="true" /> {words.invite}
          </h3>
        </div>
        <InviteForm onInvited={() => first.reload()} />
      </section>
    </>
  );
}
