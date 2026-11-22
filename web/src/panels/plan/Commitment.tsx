/** The commitment: the finish date the CEO promises, beside the projection, and the chairman's answers to it. */
import { useState } from "react";
import { post } from "../../api/client";
import { Empty } from "../../components/common";
import { formatDateTime } from "../../lib/format";
import { t } from "../../strings";
import { toMoment } from "./logic";
import { Confirm, FieldsForm, Section, StateTag, type PlanTabProps } from "./parts";

type Mode = "later" | "decline" | "move" | "reset" | null;

/** States in which the commitment stands and its date can be moved or reset. */
const STANDING = ["accepted", "at risk", "breached"];

export function Commitment({ projectId, plan, busy, run, apply }: PlanTabProps): JSX.Element {
  const [mode, setMode] = useState<Mode>(null);
  const words = t.plan.dates.commitment;
  const commitment = plan.commitment;
  const ref = { project_id: projectId };
  const close = (): void => setMode(null);

  if (!commitment) {
    return (
      <Section title={words.title} testId="commitment">
        <Empty title={words.emptyTitle} next={words.emptyNext} />
      </Section>
    );
  }

  const dateForm = (label: string, submit: string, path: "/v1/commitments/accept" | "/v1/commitments/move"): JSX.Element => (
    <FieldsForm
      fields={[{ name: "date", label, type: "date", required: true }]}
      submit={submit}
      onCancel={close}
      onSubmit={async ({ date }) => {
        await apply(() => post(path, { ...ref, date: toMoment(date ?? "") ?? "" }));
        close();
      }}
    />
  );

  return (
    <Section title={words.title} testId="commitment">
      <p className="record-text" data-testid="commitment-date">
        {commitment.date ? formatDateTime(commitment.date) : words.noDate}
      </p>
      <p className="quiet row wrap">
        <StateTag state={commitment.state} />
        <span data-testid="commitment-resets">{words.resets(commitment.resets)}</span>
      </p>
      {commitment.beside_projection ? (
        <p data-testid="commitment-beside">
          <span className="quiet">{words.beside}: </span>
          {commitment.beside_projection}
        </p>
      ) : null}
      {commitment.reason ? <p>{words.reason(commitment.reason)}</p> : null}

      {mode === "later" ? dateForm(words.acceptDate, words.acceptSubmit, "/v1/commitments/accept") : null}
      {mode === "move" ? dateForm(words.moveDate, words.moveSubmit, "/v1/commitments/move") : null}
      {mode === "decline" ? (
        <FieldsForm
          fields={[{ name: "reason", label: words.declineReason, multiline: true, required: true }]}
          submit={words.declineSubmit}
          onCancel={close}
          onSubmit={async ({ reason }) => {
            await apply(() => post("/v1/commitments/decline", { ...ref, reason: reason ?? "" }));
            close();
          }}
        />
      ) : null}
      {mode === "reset" ? (
        <Confirm
          question={words.resetSure}
          yes={words.resetYes}
          busy={busy}
          onCancel={close}
          onYes={() => void run(() => post("/v1/commitments/reset", ref)).then(close)}
        />
      ) : null}
      {mode !== null ? null : commitment.state === "proposed" ? (
        <div className="row wrap">
          <button
            type="button"
            className="button small primary"
            disabled={busy}
            onClick={() => void run(() => post("/v1/commitments/accept", ref))}
          >
            {words.accept}
          </button>
          <button type="button" className="button small" onClick={() => setMode("later")}>
            {words.acceptLater}
          </button>
          <button type="button" className="button small" onClick={() => setMode("decline")}>
            {words.decline}
          </button>
        </div>
      ) : STANDING.includes(commitment.state) ? (
        <div className="row wrap">
          <button type="button" className="button small" onClick={() => setMode("move")}>
            {words.move}
          </button>
          <button type="button" className="button small" onClick={() => setMode("reset")}>
            {words.reset}
          </button>
        </div>
      ) : null}
    </Section>
  );
}
