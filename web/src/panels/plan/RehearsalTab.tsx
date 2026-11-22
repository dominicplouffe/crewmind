/** Rehearse the project (RHS-4): one button runs the zero-token drill and shows its report. */
import { useState } from "react";
import { get } from "../../api/client";
import { ErrorNote } from "../../components/common";
import { t } from "../../strings";
import { RehearsalReport, type Report } from "./RehearsalReport";

export function RehearsalTab({ projectId }: { projectId: string }): JSX.Element {
  const words = t.founder.rehearse;
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const rehearse = async (): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      setReport(await get("/v1/projects/rehearse", { project_id: projectId }));
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <p className="quiet">{words.intro}</p>
      <button type="button" className="button primary" disabled={busy} onClick={() => void rehearse()}>
        {report ? words.again : words.run}
      </button>
      <p role="status" data-testid="rehearsing">
        {busy ? words.running : ""}
      </p>
      <ErrorNote error={error} />
      {report && !busy ? <RehearsalReport report={report} /> : null}
    </>
  );
}
