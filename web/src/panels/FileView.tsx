/** One file: pick a version, preview it, download any version, compare two text versions. */
import { ChevronLeft } from "lucide-react";
import { useEffect, useState } from "react";
import { fileUrl, get, type Artifact } from "../api/client";
import { ErrorNote } from "../components/common";
import { Loading } from "./kit";
import { isTextKind, previewKind } from "../lib/files";
import { formatBytes, formatDateTime } from "../lib/format";
import { useLoad } from "../lib/useLoad";
import { t } from "../strings";
import { Compare } from "./Compare";
import { Preview } from "./Preview";

interface Props {
  projectId: string;
  name: string;
  artifact: Artifact | undefined;
  changes: number;
  onBack(): void;
}

export function FileView({ projectId, name, artifact, changes, onBack }: Props): JSX.Element {
  const versions = useLoad(() => get("/v1/artifacts/versions", { project_id: projectId, name }), [projectId, name, changes]);
  const items = versions.data?.items ?? [];
  const latest = items.reduce((max, item) => Math.max(max, item.version), 0);
  const [version, setVersion] = useState<number | null>(null);
  const [comparing, setComparing] = useState(false);
  const [from, setFrom] = useState<number | null>(null);

  useEffect(() => {
    setVersion(null);
    setComparing(false);
    setFrom(null);
  }, [name]);

  const shown = version ?? latest;
  const current = items.find((item) => item.version === shown);
  const mediaType = artifact?.media_type ?? "";
  const canCompare = isTextKind(previewKind(name, mediaType)) && items.length > 1;
  const compareFrom = from ?? items.filter((item) => item.version < shown).reduce((max, item) => Math.max(max, item.version), 0);

  return (
    <div data-testid="file-view">
      <button type="button" className="button small ghost back-button" onClick={onBack}>
        <ChevronLeft size={16} aria-hidden="true" />
        {t.files.back}
      </button>
      <h3 className="file-name mono">{name}</h3>
      {artifact ? (
        <p className="quiet">{t.files.line(t.files.kinds[artifact.kind as keyof typeof t.files.kinds] ?? artifact.kind, artifact.status)}</p>
      ) : null}
      <ErrorNote error={versions.error} />
      {versions.loading && !versions.data ? <Loading /> : null}
      {items.length > 0 ? (
        <div className="row wrap">
          <label htmlFor="file-version">{t.files.versionLabel}</label>
          <select id="file-version" value={shown} onChange={(event) => setVersion(Number(event.target.value))}>
            {[...items].reverse().map((item) => (
              <option key={item.version} value={item.version}>
                {t.files.versionOption(item.version, item.author, formatDateTime(item.at))}
              </option>
            ))}
          </select>
          {canCompare ? (
            <button type="button" className="button small" aria-expanded={comparing} onClick={() => setComparing((value) => !value)}>
              {comparing ? t.files.stopCompare : t.files.compare}
            </button>
          ) : null}
        </div>
      ) : null}
      {comparing && canCompare ? (
        <section aria-label={t.files.compare}>
          <div className="row wrap">
            <label htmlFor="file-compare-from">{t.files.compareWith}</label>
            <select id="file-compare-from" value={compareFrom} onChange={(event) => setFrom(Number(event.target.value))}>
              {items
                .filter((item) => item.version !== shown)
                .map((item) => (
                  <option key={item.version} value={item.version}>
                    {t.files.version(item.version)}
                  </option>
                ))}
            </select>
          </div>
          {compareFrom > 0 ? (
            <Compare projectId={projectId} name={name} from={compareFrom} to={shown} />
          ) : (
            <p className="quiet">{t.files.pickOther}</p>
          )}
        </section>
      ) : current ? (
        <div className="preview" data-testid="preview">
          <Preview projectId={projectId} name={name} version={current.version} mediaType={mediaType} size={current.size} />
        </div>
      ) : null}
      {items.length > 0 ? (
        <section aria-label={t.files.downloads}>
          <h3>{t.files.downloads}</h3>
          <ul className="plain">
            {[...items].reverse().map((item) => (
              <li key={item.version}>
                <a href={fileUrl(projectId, name, item.version)} download={name}>
                  {t.files.download(item.version)}
                </a>{" "}
                <span className="quiet">{t.files.versionMeta(formatBytes(item.size), item.author, formatDateTime(item.at))}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
