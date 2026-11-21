/** Side-by-side comparison of two text versions of a file (ART-4, CHAT-16). */
import { useMemo } from "react";
import { ErrorNote, Loading } from "../components/common";
import { countChanges, sideBySide, type DiffRow } from "../lib/diff";
import { useLoad } from "../lib/useLoad";
import { t } from "../strings";
import { fetchText } from "./Preview";

const MARK: Record<DiffRow["kind"], string> = { same: "", changed: "~", added: "+", removed: "−" };

export function DiffTable({
  rows,
  leftLabel,
  rightLabel,
}: {
  rows: DiffRow[];
  leftLabel: string;
  rightLabel: string;
}): JSX.Element {
  const counts = countChanges(rows);
  return (
    <>
      <p role="status">{counts.added + counts.removed === 0 ? t.compare.same : t.compare.summary(counts.added, counts.removed)}</p>
      {/* The scroll area is focusable so keyboard users can scroll long lines. */}
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
      <div className="table-scroll" tabIndex={0} role="region" aria-label={t.compare.tableLabel}>
        <table className="diff" data-testid="diff-table">
          <thead>
            <tr>
              <th scope="col" className="visually-hidden">
                {t.compare.change}
              </th>
              <th scope="col" colSpan={2}>
                {leftLabel}
              </th>
              <th scope="col" colSpan={2}>
                {rightLabel}
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index} className={`diff-${row.kind}`}>
                <td className="diff-mark">
                  <span aria-hidden="true">{MARK[row.kind]}</span>
                  <span className="visually-hidden">{t.compare.kinds[row.kind]}</span>
                </td>
                <td className="diff-number">{row.leftNumber ?? ""}</td>
                <td className={row.left === null ? "diff-gap" : "diff-left"}>{row.left ?? ""}</td>
                <td className="diff-number">{row.rightNumber ?? ""}</td>
                <td className={row.right === null ? "diff-gap" : "diff-right"}>{row.right ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

interface Props {
  projectId: string;
  name: string;
  from: number;
  to: number;
}

export function Compare({ projectId, name, from, to }: Props): JSX.Element {
  const texts = useLoad(
    () => Promise.all([fetchText(projectId, name, from), fetchText(projectId, name, to)]),
    [projectId, name, from, to],
  );
  const rows = useMemo(() => (texts.data ? sideBySide(texts.data[0], texts.data[1]) : []), [texts.data]);
  if (texts.error) return <ErrorNote error={texts.error} />;
  if (!texts.data) return <Loading />;
  return <DiffTable rows={rows} leftLabel={t.files.version(from)} rightLabel={t.files.version(to)} />;
}
