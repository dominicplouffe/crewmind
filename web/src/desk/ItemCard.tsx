/**
 * A decision item as a compact card (HUM-1, HUM-2): the ask in plain words, what it is about in the
 * filer's own words, who asks, by when and how much, and the buttons. Everything else (the
 * recommendation, what happens if nothing is done, the fields, the server's title, the history, a
 * note, more time, setting it aside) waits behind "Details". Once settled, the card folds to one
 * quiet line. Every word about the item comes from the server; this only arranges it.
 */
import { AlarmClock, AlertTriangle, CheckCircle2, ChevronDown, FolderClosed, MessageSquare, Sparkles } from "lucide-react";
import { useContext, useEffect, useId, useState } from "react";
import { Link } from "react-router-dom";
import { get } from "../api/client";
import { ErrorNote } from "../components/common";
import { formatDateTime } from "../lib/format";
import { fromNow } from "../lib/humanize";
import { useLoad } from "../lib/useLoad";
import { AgentText } from "../panels/board/parts";
import { t } from "../strings";
import { Avatar } from "../ui/Avatar";
import { Skeleton } from "../ui/Skeleton";
import { Clamp } from "./Clamp";
import { ItemsContext } from "./context";
import { headlineOf, settledWords } from "./headline";
import { answersQuestion, ItemActions, ItemMore } from "./ItemActions";
import { ItemFields } from "./ItemFields";
import { textField, type Item } from "./logic";
import { Snooze } from "./Snooze";
import { askerOf, deadlineWords } from "./when";
import { useAgentName } from "../crew/names";

export interface ItemProject {
  id: string;
  name: string;
}

interface Props {
  item: Item;
  /** Called after the person decided, noted or changed something on the item. */
  onChanged(item: Item): void;
  /** The project, named on the card where several projects share a list (Home). */
  project?: ItemProject;
  /** Headline, due and the first action only: the slim stack above the chat. */
  slim?: boolean;
  /** In a slim card, what opens the full card (a question is answered there, not blind). */
  onOpen?(): void;
}

function StateWord({ item }: { item: Item }): JSX.Element {
  const words = t.decisions.card;
  // The state goes without saying on the card; it stays for screen readers.
  return (
    <span className="visually-hidden" data-testid="item-state">
      {words.stateOf}: {t.decisions.states[item.state] ?? item.state}
    </span>
  );
}

function History({ item }: { item: Item }): JSX.Element {
  const words = t.decisions.compact;
  const detail = useLoad(() => get("/v1/items/show", { project_id: item.project_id, item_id: item.id }), [item]);
  if (!detail.data) return detail.error ? <ErrorNote error={detail.error} /> : <Skeleton lines={2} label={words.loadingHistory} />;
  if (detail.data.history.length === 0) return <p className="quiet">{words.noHistory}</p>;
  return (
    <ol className="plain dcard-history" aria-label={t.decisions.items.historyLabel(item.title)}>
      {detail.data.history.map((line, index) => (
        <li key={index}>
          <time dateTime={line.at}>{formatDateTime(line.at)}</time> {words.historyLine(line.actor_kind, line.what)}
        </li>
      ))}
    </ol>
  );
}

/** What waits behind "Details": present in the page while hidden, and loaded further only when shown. */
function Details({ item, open, id, onChanged }: { item: Item; open: boolean; id: string; onChanged(item: Item): void }): JSX.Element {
  const words = t.decisions.compact;
  const card = t.decisions.card;
  const inChat = useContext(ItemsContext) !== null;
  const live = item.actions.length > 0;
  const when = deadlineWords(item.deadline, item.default_outcome);
  const head = headlineOf(item);
  const recommendation = item.recommendation.trim();
  const ceoDefault = item.kind === "question" && !item.if_declined ? textField(item.fields, "default") : null;
  return (
    <div className="dcard-details" id={id} hidden={!open}>
      {live && when.ifNothing ? (
        <p className="dcard-default" data-testid="item-default">
          {when.ifNothing}
        </p>
      ) : null}
      <dl className="dcard-facts">
        {recommendation && recommendation !== head.subject ? (
          <div>
            <dt>{card.recommendation}</dt>
            <dd>
              <AgentText text={recommendation} />
            </dd>
          </div>
        ) : null}
        {ceoDefault ? (
          <div>
            <dt>{t.decisions.question.ceoDefaultLabel}</dt>
            <dd>
              <AgentText text={ceoDefault} />
            </dd>
          </div>
        ) : null}
        {item.if_declined ? (
          <div>
            <dt>{card.ifDeclined}</dt>
            <dd>
              <AgentText text={item.if_declined} />
            </dd>
          </div>
        ) : null}
        {item.chairman_note ? (
          <div>
            <dt>{card.yourNote}</dt>
            <dd>
              <AgentText text={item.chairman_note} />
            </dd>
          </div>
        ) : null}
        <div>
          <dt>{words.serverTitle}</dt>
          <dd>
            <AgentText text={item.title} />
          </dd>
        </div>
      </dl>
      <ItemFields item={item} onChanged={onChanged} />
      {open ? (
        <div className="dcard-section">
          <p className="dcard-label">{words.history}</p>
          <History item={item} />
        </div>
      ) : null}
      {live ? (
        <div className="dcard-tools">
          <ItemMore item={item} onChanged={onChanged} />
          {!inChat ? (
            <Link to={`/projects/${item.project_id}`} className="button small ghost">
              <MessageSquare size={14} aria-hidden="true" />
              {words.discuss}
              <span className="visually-hidden"> {card.of(item.title)}</span>
            </Link>
          ) : null}
        </div>
      ) : null}
      {live && item.waits_on_you ? <Snooze item={item} onDone={() => onChanged(item)} /> : null}
    </div>
  );
}

/** Who asks, by when, the size, and the project when the list spans several. */
function Meta({ item, project, size }: { item: Item; project?: ItemProject; size: string | null }): JSX.Element {
  const asker = askerOf(item.filed_by, item.kind, useAgentName());
  const live = item.actions.length > 0;
  const when = deadlineWords(item.deadline, item.default_outcome);
  const DueIcon = when.urgency === "overdue" ? AlertTriangle : AlarmClock;
  return (
    <p className="dcard-meta">
      {project ? (
        <Link to={`/projects/${project.id}`} className="dcard-project">
          <FolderClosed size={13} aria-hidden="true" />
          {project.name}
        </Link>
      ) : null}
      <span className="dcard-who">
        {asker.name ? <Avatar name={asker.name} hueKey={asker.seat} kind="agent" size="xs" /> : <Sparkles size={13} aria-hidden="true" className="dcard-who-icon" />}
        <span className="visually-hidden">{asker.line}: </span>
        <span aria-hidden="true">{asker.who}</span>
      </span>
      {live ? (
        <span className={`dcard-due urgency-${when.urgency}`}>
          <DueIcon size={13} aria-hidden="true" />
          <span data-testid="item-deadline">{when.line}</span>
        </span>
      ) : null}
      {size ? <span className="dcard-size tabular">{size}</span> : null}
    </p>
  );
}

/** A settled item: one quiet line that opens to show what was decided. */
function Settled({ item, onChanged }: { item: Item; onChanged(item: Item): void }): JSX.Element {
  const head = headlineOf(item);
  const id = useId();
  const [open, setOpen] = useState(false);
  return (
    <details
      className="dcard is-closed"
      aria-label={t.decisions.card.label(item.title)}
      data-testid="item-card"
      data-item-id={item.id}
      data-item-kind={item.kind}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="dcard-settled">
        <CheckCircle2 size={15} aria-hidden="true" className="dcard-settled-icon" />
        <span className="dcard-settled-what" data-testid="item-outcome">
          {settledWords(item)}
        </span>
        <span className="dcard-settled-subject">
          <AgentText text={head.subject ?? head.ask} />
        </span>
        {item.closed_at ? (
          <time className="dcard-time" dateTime={item.closed_at} title={formatDateTime(item.closed_at)}>
            {fromNow(item.closed_at)}
          </time>
        ) : null}
        <StateWord item={item} />
        <ChevronDown size={14} aria-hidden="true" className="dcard-chevron" />
      </summary>
      <Details item={item} open={open} id={id} onChanged={onChanged} />
    </details>
  );
}

export function ItemCard({ item: given, onChanged, project, slim = false, onOpen }: Props): JSX.Element {
  const words = t.decisions.compact;
  const card = t.decisions.card;
  // The server's answer to a button press is shown at once; the next load replaces it.
  const [answered, setAnswered] = useState<Item | null>(null);
  const [open, setOpen] = useState(false);
  const detailsId = useId();
  useEffect(() => setAnswered(null), [given]);
  const item = answered ?? given;
  const live = item.actions.length > 0;
  const closed = item.closed_at !== null || item.outcome !== null;
  const head = headlineOf(item);
  const when = deadlineWords(item.deadline, item.default_outcome);
  const urgent = live && (when.urgency === "overdue" || when.urgency === "today") ? ` is-${when.urgency}` : "";

  const changed = (view: Item): void => {
    setAnswered(view);
    onChanged(view);
  };

  if (!live && closed) return <Settled item={item} onChanged={changed} />;

  if (slim) {
    const due = item.deadline ? (when.urgency === "overdue" ? when.badge : fromNow(item.deadline)) : null;
    return (
      <section
        className={`dcard is-slim${urgent}`}
        aria-label={card.label(item.title)}
        data-testid="needs-stack-item"
        data-item-id={item.id}
        data-item-kind={item.kind}
      >
        <p className="dcard-slim-text">
          <span className="dcard-ask">{head.ask}</span>
          {head.subject ? (
            <span className="dcard-slim-subject">
              <AgentText text={head.subject} />
            </span>
          ) : null}
        </p>
        {due ? (
          <span className={`dcard-due urgency-${when.urgency}`} title={when.line}>
            <span className="visually-hidden">{when.line}</span>
            <span aria-hidden="true">{due}</span>
          </span>
        ) : null}
        {answersQuestion(item) && onOpen ? (
          <button type="button" className="button small primary" onClick={onOpen}>
            {card.actions.answer}…<span className="visually-hidden"> {card.of(item.title)}</span>
          </button>
        ) : (
          <ItemActions item={item} onChanged={changed} only="primary" />
        )}
      </section>
    );
  }

  const toggle = (
    <button
      type="button"
      className="button small ghost dcard-toggle"
      aria-expanded={open}
      aria-controls={detailsId}
      onClick={() => setOpen((value) => !value)}
    >
      {open ? words.hideDetails : words.details}
      <span className="visually-hidden"> {words.detailsOf(item.title)}</span>
      <ChevronDown size={14} aria-hidden="true" className="dcard-chevron" />
    </button>
  );

  return (
    <section
      className={`dcard is-open${urgent}`}
      aria-label={card.label(item.title)}
      data-testid="item-card"
      data-item-id={item.id}
      data-item-kind={item.kind}
      tabIndex={-1}
    >
      <h3 className="dcard-ask">{head.ask}</h3>
      <StateWord item={item} />
      {head.subject ? (
        <Clamp className="dcard-subject" moreLabel={words.more} lessLabel={words.less} moreHint={words.moreOf}>
          <AgentText text={head.subject} />
        </Clamp>
      ) : null}
      <Meta item={item} project={project} size={head.size} />
      {live ? (
        <ItemActions item={item} onChanged={changed} aside={toggle} />
      ) : (
        <div className="dcard-actions">
          <span className="quiet">{card.openNoActions}</span>
          {toggle}
        </div>
      )}
      <Details item={item} open={open} id={detailsId} onChanged={changed} />
    </section>
  );
}

/** The card for the item a chat line is about. It loads the item, and reloads while it is still open. */
export function ChatItemCard({ itemId }: { itemId: number }): JSX.Element {
  const scope = useContext(ItemsContext);
  const projectId = scope?.projectId ?? "";
  const [settled, setSettled] = useState(false);
  // A settled item no longer changes, so it is not asked for again on every change in the project.
  const watch = settled ? 0 : (scope?.changes ?? 0);
  const item = useLoad(() => get("/v1/items/show", { project_id: projectId, item_id: itemId }), [projectId, itemId, watch]);
  const data = item.data ?? scope?.known?.get(itemId);
  const closedAt = data?.closed_at ?? null;
  useEffect(() => {
    if (closedAt !== null) setSettled(true);
  }, [closedAt]);

  if (!data) {
    return item.error ? (
      <ErrorNote error={item.error} />
    ) : (
      <div className="dcard is-loading">
        <Skeleton lines={3} label={t.decisions.card.loading} />
      </div>
    );
  }
  return <ItemCard item={data} onChanged={() => scope?.onChanged()} />;
}
