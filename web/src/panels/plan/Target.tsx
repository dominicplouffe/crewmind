/** The target date: when the chairman wants the work done, shown beside the projection. */
import { Crosshair } from "lucide-react";
import { useState } from "react";
import { post } from "../../api/client";
import { Empty } from "../kit";
import { formatDateTime } from "../../lib/format";
import { t } from "../../strings";
import { toMoment } from "./logic";
import { FieldsForm, Section, type PlanTabProps } from "./parts";

export function Target({ projectId, plan, busy, run, apply }: PlanTabProps): JSX.Element {
  const [setting, setSetting] = useState(false);
  const words = t.plan.dates.target;
  const target = plan.target;

  return (
    <Section title={words.title} testId="target">
      {target ? (
        <>
          <p className="record-text" data-testid="target-date">
            {formatDateTime(target.date)}
          </p>
          {target.source ? <p className="quiet">{words.source(target.source)}</p> : null}
          <p data-testid="target-beside">
            <span className="quiet">{words.beside}: </span>
            {target.beside_projection}
          </p>
        </>
      ) : setting ? null : (
        <Empty icon={Crosshair} title={words.emptyTitle} next={words.emptyNext} />
      )}
      {setting ? (
        <FieldsForm
          fields={[
            { name: "date", label: words.date, type: "date", required: true },
            { name: "source", label: words.sourceLabel, hint: words.sourceHint, initial: target?.source ?? "" },
          ]}
          submit={words.submit}
          onCancel={() => setSetting(false)}
          onSubmit={async ({ date, source }) => {
            await apply(() => post("/v1/plan/set_target", { project_id: projectId, date: toMoment(date ?? ""), source: source ?? "" }));
            setSetting(false);
          }}
        />
      ) : (
        <div className="row wrap">
          <button type="button" className="button small" onClick={() => setSetting(true)}>
            {target ? words.change : words.set}
          </button>
          {target ? (
            <button
              type="button"
              className="button small"
              disabled={busy}
              onClick={() => void run(() => post("/v1/plan/set_target", { project_id: projectId, source: "" }))}
            >
              {words.clear}
            </button>
          ) : null}
        </div>
      )}
    </Section>
  );
}
