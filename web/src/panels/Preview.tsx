/** Shows one version of a file (CHAT-16). HTML runs only in a sandboxed frame with no network. */
import { useEffect, useMemo, useState } from "react";
import { errorFrom, fileUrl } from "../api/client";
import { ErrorNote, Markdown, Pre } from "../components/common";
import { Loading } from "./kit";
import { parseCsv } from "../lib/csv";
import { codeLanguage, isTextKind, previewKind, sandboxedDocument } from "../lib/files";
import { formatBytes } from "../lib/format";
import { highlight } from "../lib/markdown";
import { useLoad } from "../lib/useLoad";
import { t } from "../strings";

/** Text larger than this is offered as a download instead of drawn in the page. */
const MAX_TEXT_PREVIEW_BYTES = 2 * 1024 * 1024;
const MAX_TABLE_ROWS = 500;

interface Props {
  projectId: string;
  name: string;
  version: number;
  mediaType: string;
  size: number;
}

export async function fetchText(projectId: string, name: string, version: number): Promise<string> {
  const response = await fetch(fileUrl(projectId, name, version), { credentials: "same-origin" });
  if (!response.ok) throw await errorFrom(response);
  return response.text();
}

function CsvTable({ text, name }: { text: string; name: string }): JSX.Element {
  const rows = useMemo(() => parseCsv(text), [text]);
  const [head, ...body] = rows;
  if (!head) return <p className="quiet">{t.preview.emptyFile}</p>;
  const shown = body.slice(0, MAX_TABLE_ROWS);
  return (
    <>
      {/* The scroll area is focusable so keyboard users can scroll wide tables. */}
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
      <div className="table-scroll" tabIndex={0} role="region" aria-label={t.preview.tableLabel(name)}>
        <table className="grid" data-testid="csv-table">
          <thead>
            <tr>
              {head.map((cell, index) => (
                <th key={index} scope="col">
                  {cell}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, index) => (
                  <td key={index}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {body.length > shown.length ? <p className="quiet">{t.preview.rowsCut(shown.length, body.length)}</p> : null}
    </>
  );
}

function TextPreview({ projectId, name, version, kind }: Props & { kind: ReturnType<typeof previewKind> }): JSX.Element {
  const text = useLoad(() => fetchText(projectId, name, version), [projectId, name, version]);
  if (text.error) return <ErrorNote error={text.error} />;
  if (text.data === undefined) return <Loading />;
  if (kind === "markdown") return <Markdown source={text.data} />;
  if (kind === "csv") return <CsvTable text={text.data} name={name} />;
  if (kind === "html") {
    return (
      <iframe
        className="html-frame"
        title={t.preview.htmlTitle(name)}
        sandbox=""
        referrerPolicy="no-referrer"
        srcDoc={sandboxedDocument(text.data)}
        data-testid="html-frame"
      />
    );
  }
  if (kind === "code") {
    const html = highlight(text.data, codeLanguage(name));
    // `highlight` escapes the text and adds only its own span tags.
    return (
      <Pre className="file-text">
        <code className="hljs" dangerouslySetInnerHTML={{ __html: html }} />
      </Pre>
    );
  }
  return (
    <Pre className="file-text">
      {text.data}
    </Pre>
  );
}

function PdfPreview({ projectId, name, version }: Props): JSX.Element {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let made: string | null = null;
    let current = true;
    fetch(fileUrl(projectId, name, version), { credentials: "same-origin" })
      .then(async (response) => {
        if (!response.ok) throw await errorFrom(response);
        const bytes = await response.arrayBuffer();
        if (!current) return;
        made = URL.createObjectURL(new Blob([bytes], { type: "application/pdf" }));
        setUrl(made);
      })
      .catch((reason: unknown) => {
        if (current) setError(reason);
      });
    return () => {
      current = false;
      if (made) URL.revokeObjectURL(made);
    };
  }, [projectId, name, version]);

  if (error) return <ErrorNote error={error} />;
  if (!url) return <Loading />;
  return (
    <object className="pdf-frame" data={url} type="application/pdf" aria-label={t.preview.pdfTitle(name)}>
      <p>{t.preview.pdfFallback}</p>
    </object>
  );
}

export function Preview(props: Props): JSX.Element {
  const { projectId, name, version, mediaType, size } = props;
  const kind = previewKind(name, mediaType);
  const url = fileUrl(projectId, name, version);

  if (kind === "none") return <p className="quiet">{t.preview.none}</p>;
  if (isTextKind(kind)) {
    if (size > MAX_TEXT_PREVIEW_BYTES) return <p className="quiet">{t.preview.tooBig(formatBytes(size))}</p>;
    return <TextPreview {...props} kind={kind} />;
  }
  if (kind === "image") return <img className="file-image" src={url} alt={t.preview.imageAlt(name)} />;
  if (kind === "pdf") return <PdfPreview {...props} />;
  if (kind === "audio") {
    // Uploaded recordings carry no captions; the file can be downloaded.
    // eslint-disable-next-line jsx-a11y/media-has-caption
    return <audio controls src={url} aria-label={t.preview.audioLabel(name)} />;
  }
  // eslint-disable-next-line jsx-a11y/media-has-caption
  return <video controls className="file-video" src={url} aria-label={t.preview.videoLabel(name)} />;
}
