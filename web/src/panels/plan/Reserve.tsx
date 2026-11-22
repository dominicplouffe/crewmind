/** The CEO's reserve with each draw from it, and the CEO's requests for more budget. */
import { useState } from "react";
import { post } from "../../api/client";
import { formatDateTime, formatNumber } from "../../lib/format";
import { t } from "../../strings";
import { AgentText } from "../board/parts";
import { wholeNumber } from "./logic";
import { ActionButton, Confirm, FieldsForm, Section, StateTag, type PlanTabProps } from "./parts";

export function Reserve({ projectId, plan, busy, run }: PlanTabProps): JSX.Element {
  /** The draw being asked about: a positive id to cancel it, a negative one to deny it. */
  const [confirming, setConfirming] = useState<number | null>(null);
  const words = t.plan.dates.reserve;
  const reserve = plan.reserve;
  const close = (): void => setConfirming(null);
  const answer = (drawId: number, approve: boolean): Promise<boolean> =>
    run(() => post("/v1/reserve/answer", { project_id: projectId, draw_id: drawId, approve }));

  return (
    <Section title={words.title} testId="reserve">
      <p>{words.size(formatNumber(reserve.size))}</p>
      <p data-testid="reserve-can-draw">{reserve.can_draw ? words.canDraw : words.cannotDraw}</p>
      <p className="quiet">{reserve.arithmetic}</p>
      {reserve.draws.length === 0 ? <p className="quiet">{words.none}</p> : null}
      <ul className="records plain" aria-label={words.listLabel}>
        {reserve.draws.map((draw) => (
          <li key={draw.id} data-testid="draw" className={draw.state === "requested" || draw.state === "drawn" ? "" : "is-past"}>
            <p className="record-text">
              <AgentText text={draw.reason} />
            </p>
            <p className="quiet row wrap">
              <StateTag state={draw.state} />
              <span>{words.draw(formatNumber(draw.tokens), draw.drawn_by, formatDateTime(draw.at))}</span>
            </p>
            <p className="quiet">{draw.arithmetic}</p>
            {confirming === -draw.id ? (
              <Confirm question={words.denySure} yes={words.denyYes} busy={busy} onCancel={close} onYes={() => void answer(draw.id, false).then(close)} />
            ) : confirming === draw.id ? (
              <Confirm
                question={words.cancelSure}
                yes={words.cancelYes}
                busy={busy}
                onCancel={close}
                onYes={() => void run(() => post("/v1/reserve/cancel", { project_id: projectId, draw_id: draw.id })).then(close)}
              />
            ) : draw.state === "requested" ? (
              <div className="row wrap">
                <ActionButton label={words.approve} of={words.of(draw.id)} primary disabled={busy} onClick={() => void answer(draw.id, true)} />
                <ActionButton label={words.deny} of={words.of(draw.id)} onClick={() => setConfirming(-draw.id)} />
              </div>
            ) : draw.state === "drawn" ? (
              <button type="button" className="button small" onClick={() => setConfirming(draw.id)}>
                {words.cancel}
                <span className="visually-hidden"> ({words.of(draw.id)})</span>
              </button>
            ) : null}
          </li>
        ))}
      </ul>
    </Section>
  );
}

export function Raises({ projectId, plan, busy, run, apply }: PlanTabProps): JSX.Element {
  /** The request being answered: a positive id to grant another amount, a negative one to decline it. */
  const [asking, setAsking] = useState<number | null>(null);
  const words = t.plan.dates.raises;
  const close = (): void => setAsking(null);

  return (
    <Section title={words.title} testId="raises">
      {plan.raises.length === 0 ? <p className="quiet">{words.none}</p> : null}
      <ul className="records plain" aria-label={words.listLabel}>
        {plan.raises.map((request) => {
          const ref = { project_id: projectId, request_id: request.id };
          return (
            <li key={request.id} data-testid="raise" className={request.state === "pending" ? "" : "is-past"}>
              <p className="record-text">{words.what[request.what] ?? words.whatOther(request.what)}</p>
              <p className="quiet row wrap">
                <StateTag state={request.state} />
                <span>{words.amount(formatNumber(request.amount))}</span>
                {request.granted != null ? <span>{words.granted(formatNumber(request.granted))}</span> : null}
              </p>
              <p className="quiet">{request.arithmetic}</p>
              <p>{words.ifDeclined(request.if_declined)}</p>
              {request.state !== "pending" ? null : asking === request.id ? (
                <FieldsForm
                  fields={[{ name: "amount", label: words.otherAmount, type: "number", required: true, initial: String(request.amount) }]}
                  submit={words.otherSubmit}
                  onCancel={close}
                  onSubmit={async ({ amount }) => {
                    await apply(() => post("/v1/raises/answer", { ...ref, approve: true, amount: wholeNumber(amount ?? "") }));
                    close();
                  }}
                />
              ) : asking === -request.id ? (
                <Confirm
                  question={words.declineSure}
                  yes={words.declineYes}
                  busy={busy}
                  onCancel={close}
                  onYes={() => void run(() => post("/v1/raises/answer", { ...ref, approve: false })).then(close)}
                />
              ) : (
                <div className="row wrap">
                  <ActionButton
                    label={words.approve}
                    of={words.of(request.id)}
                    primary
                    disabled={busy}
                    onClick={() => void run(() => post("/v1/raises/answer", { ...ref, approve: true }))}
                  />
                  <ActionButton label={words.approveOther} of={words.of(request.id)} onClick={() => setAsking(request.id)} />
                  <ActionButton label={words.decline} of={words.of(request.id)} onClick={() => setAsking(-request.id)} />
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </Section>
  );
}
