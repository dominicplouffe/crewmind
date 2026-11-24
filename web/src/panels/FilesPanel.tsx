/** Deliverables and files (ART-3): the latest version of each, with older ones folded away. */
import { FileText, FolderOpen, Lock } from "lucide-react";
import { useState } from "react";
import { get, post, type Artifact, type Schemas } from "../api/client";
import { ErrorNote } from "../components/common";
import { Empty, Loading } from "./kit";
import { formatBytes, formatDateTime } from "../lib/format";
import { fromNow } from "../lib/humanize";
import { useLoad } from "../lib/useLoad";
import { t } from "../strings";
import { FileView } from "./FileView";
import { useAgentName } from "../squad/names";

type Kind = Schemas["Kind"];
const KINDS: Kind[] = ["deliverable", "working", "upload", "report"];

interface Props {
  projectId: string;
  changes: number;
  file: string | undefined;
  onFile(name: string | undefined): void;
}

function FileRow({
  artifact,
  onOpen,
  onChanged,
  projectId,
}: {
  artifact: Artifact;
  projectId: string;
  onOpen(): void;
  onChanged(): void;
}): JSX.Element {
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const nameOf = useAgentName();

  const act = async (work: () => Promise<unknown>): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      await work();
      onChanged();
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  };
  const ref = { project_id: projectId, name: artifact.name };

  return (
    <li className="file-row" data-testid="file-row">
      <span className="row-icon" aria-hidden="true">
        <FileText size={18} />
      </span>
      <div className="row-main">
        <button type="button" className="row-title" onClick={onOpen}>
          {artifact.name}
        </button>
        <p className="row-meta">
          <span className="badge">{t.files.kinds[artifact.kind as Kind] ?? artifact.kind}</span>
          {artifact.status ? <span className="badge">{artifact.status}</span> : null}
          {artifact.locked ? (
            <span className="badge badge-warning">
              <Lock size={11} aria-hidden="true" />
              {t.files.locked}
            </span>
          ) : null}
          {artifact.mark ? <span className="badge badge-accent">{t.files.marked(artifact.mark)}</span> : null}
        </p>
        <p className="row-meta">
          <span title={formatDateTime(artifact.last_change)}>
            {t.files.changedAgo(fromNow(artifact.last_change), nameOf(artifact.last_author).name)}
          </span>
          <span>{t.files.versions(artifact.versions)}</span>
          <span>{formatBytes(artifact.size)}</span>
        </p>
        <div className="row-actions">
          <button
            type="button"
            className="button small ghost"
            disabled={busy}
            onClick={() => void act(() => post(artifact.locked ? "/v1/artifacts/unlock" : "/v1/artifacts/lock", ref))}
          >
            {artifact.locked ? t.files.unlock : t.files.lock}
            <span className="visually-hidden"> {artifact.name}</span>
          </button>
          {artifact.kind === "upload"
            ? (["reference", "example"] as const).map((mark) => (
                <button
                  key={mark}
                  type="button"
                  className="button small ghost"
                  disabled={busy}
                  aria-pressed={artifact.mark === mark}
                  onClick={() => void act(() => post("/v1/artifacts/mark", { ...ref, mark }))}
                >
                  {t.files.markAs[mark]}
                  <span className="visually-hidden"> {artifact.name}</span>
                </button>
              ))
            : null}
        </div>
        <ErrorNote error={error} />
      </div>
    </li>
  );
}

export function FilesPanel({ projectId, changes, file, onFile }: Props): JSX.Element {
  const [kind, setKind] = useState<Kind | "">("");
  const list = useLoad(
    () => get("/v1/artifacts/list", { project_id: projectId, kind: kind || undefined, include_superseded: true }),
    [projectId, kind, changes],
  );
  const items = list.data?.items ?? [];
  const current = items.filter((item) => !item.superseded_by);
  const superseded = items.filter((item) => item.superseded_by);

  if (file) {
    return (
      <FileView
        projectId={projectId}
        name={file}
        artifact={items.find((item) => item.name === file)}
        changes={changes}
        onBack={() => onFile(undefined)}
      />
    );
  }

  const row = (artifact: Artifact): JSX.Element => (
    <FileRow
      key={artifact.name}
      artifact={artifact}
      projectId={projectId}
      onOpen={() => onFile(artifact.name)}
      onChanged={list.reload}
    />
  );

  return (
    <>
      <div className="row wrap file-filter">
        <label htmlFor="files-kind">{t.files.show}</label>
        <select id="files-kind" value={kind} onChange={(event) => setKind(event.target.value as Kind | "")}>
          <option value="">{t.files.all}</option>
          {KINDS.map((value) => (
            <option key={value} value={value}>
              {t.files.kindsPlural[value]}
            </option>
          ))}
        </select>
      </div>
      <ErrorNote error={list.error} />
      {list.loading && !list.data ? <Loading /> : null}
      {list.data && items.length === 0 ? <Empty icon={FolderOpen} title={t.files.emptyTitle} next={t.files.emptyNext} /> : null}
      <ul className="rows plain">{current.map(row)}</ul>
      {superseded.length > 0 ? (
        <details>
          <summary>{t.files.superseded(superseded.length)}</summary>
          <ul className="rows plain">{superseded.map(row)}</ul>
        </details>
      ) : null}
      {list.data ? <p className="quiet files-footer">{t.files.storage(formatBytes(list.data.storage_used))}</p> : null}
    </>
  );
}
