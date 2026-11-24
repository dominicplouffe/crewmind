/**
 * A small, real preview of a file for a card (CHAT-16): the opening of a document, a few lines of
 * code, an image, the top of a table, or a web page in a locked frame. Text is fetched only once
 * the card is on screen, and kept while the file is unchanged.
 */
import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { FileArchive, FileAudio, FileCode, FileImage, FileText, FileVideo, Globe, Sheet as SheetIcon, File } from "lucide-react";
import { errorFrom, fileUrl, type Artifact } from "../api/client";
import { Markdown } from "../components/common";
import { parseCsv } from "../lib/csv";
import { codeLanguage, isTextKind, previewKind, sandboxedDocument, type PreviewKind } from "../lib/files";
import { highlight } from "../lib/markdown";
import { deliverables as words } from "../strings.squad";
import { excerptLines, markdownExcerpt } from "./logic";

/** Text files larger than this show an icon instead of an excerpt, so a card never pulls a big file. */
const MAX_EXCERPT_BYTES = 512 * 1024;
const CODE_LINES = 14;
const TABLE_ROWS = 5;
const TABLE_COLUMNS = 4;
const MARKDOWN_CHARS = 900;

const cache = new Map<string, Promise<string>>();

function textOf(projectId: string, item: Artifact): Promise<string> {
  const key = `${projectId}/${item.name}@${item.versions}/${item.last_change}`;
  let pending = cache.get(key);
  if (!pending) {
    pending = fetch(fileUrl(projectId, item.name), { credentials: "same-origin" }).then(async (response) => {
      if (!response.ok) throw await errorFrom(response);
      return response.text();
    });
    pending.catch(() => cache.delete(key));
    cache.set(key, pending);
  }
  return pending;
}

/** True once the element has come near the screen (always true where IntersectionObserver is missing). */
function useSeen<T extends Element>(): [RefObject<T>, boolean] {
  const ref = useRef<T>(null);
  const [seen, setSeen] = useState(typeof IntersectionObserver === "undefined");
  useEffect(() => {
    if (seen || !ref.current) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setSeen(true);
          observer.disconnect();
        }
      },
      { rootMargin: "200px" },
    );
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, [seen]);
  return [ref, seen];
}

function useText(projectId: string, item: Artifact, enabled: boolean): { text?: string; failed: boolean } {
  const [state, setState] = useState<{ text?: string; failed: boolean }>({ failed: false });
  useEffect(() => {
    if (!enabled) return;
    let current = true;
    textOf(projectId, item)
      .then((text) => current && setState({ text, failed: false }))
      .catch(() => current && setState({ failed: true }));
    return () => {
      current = false;
    };
    // The file only changes when its version or change time does.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, item.name, item.versions, item.last_change, enabled]);
  return state;
}

function KindIcon({ kind, name }: { kind: PreviewKind; name: string }): JSX.Element {
  const size = 28;
  const ext = name.toLowerCase();
  if (kind === "html") return <Globe size={size} aria-hidden="true" />;
  if (kind === "image") return <FileImage size={size} aria-hidden="true" />;
  if (kind === "csv") return <SheetIcon size={size} aria-hidden="true" />;
  if (kind === "code") return <FileCode size={size} aria-hidden="true" />;
  if (kind === "audio") return <FileAudio size={size} aria-hidden="true" />;
  if (kind === "video") return <FileVideo size={size} aria-hidden="true" />;
  if (/\.(zip|tar|gz|tgz|7z)$/.test(ext)) return <FileArchive size={size} aria-hidden="true" />;
  if (kind === "none") return <File size={size} aria-hidden="true" />;
  return <FileText size={size} aria-hidden="true" />;
}

function IconThumb({ kind, name, label }: { kind: PreviewKind; name: string; label?: string }): JSX.Element {
  return (
    <div className={`thumb thumb-icon thumb-${kind}`}>
      <KindIcon kind={kind} name={name} />
      {label ? <span className="thumb-label">{label}</span> : null}
    </div>
  );
}

function MiniTable({ text }: { text: string }): JSX.Element {
  const rows = useMemo(() => parseCsv(text.slice(0, 8000)).slice(0, TABLE_ROWS + 1), [text]);
  const [head, ...body] = rows;
  if (!head) return <p className="thumb-empty">{words.emptyFile}</p>;
  return (
    <table className="thumb-table">
      <thead>
        <tr>
          {head.slice(0, TABLE_COLUMNS).map((cell, index) => (
            <th key={index}>{cell}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {body.map((row, rowIndex) => (
          <tr key={rowIndex}>
            {row.slice(0, TABLE_COLUMNS).map((cell, index) => (
              <td key={index}>{cell}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function Thumb({ projectId, item }: { projectId: string; item: Artifact }): JSX.Element {
  const kind = previewKind(item.name, item.media_type);
  const textual = isTextKind(kind) && item.size <= MAX_EXCERPT_BYTES;
  const [ref, seen] = useSeen<HTMLDivElement>();
  const { text, failed } = useText(projectId, item, textual && seen);

  if (kind === "image") {
    return (
      <div className="thumb thumb-image">
        <img src={fileUrl(projectId, item.name)} alt="" loading="lazy" decoding="async" />
      </div>
    );
  }
  if (kind === "pdf") return <IconThumb kind={kind} name={item.name} label={words.pdf} />;
  if (kind === "audio") return <IconThumb kind={kind} name={item.name} label={words.audio} />;
  if (kind === "video") return <IconThumb kind={kind} name={item.name} label={words.video} />;
  if (!textual) return <IconThumb kind={kind} name={item.name} label={kind === "html" ? words.webPage : words.file} />;

  let body: JSX.Element;
  if (failed) body = <IconThumb kind={kind} name={item.name} label={words.previewFailed} />;
  else if (text === undefined) body = <span className="skeleton thumb-skeleton" />;
  else if (text.trim() === "") body = <p className="thumb-empty">{words.emptyFile}</p>;
  else if (kind === "markdown") body = <Markdown source={markdownExcerpt(text, MARKDOWN_CHARS)} className="thumb-md" />;
  else if (kind === "csv") body = <MiniTable text={text} />;
  else if (kind === "html") {
    body = (
      <div className="thumb-frame">
        <iframe
          title={words.webPage}
          sandbox=""
          referrerPolicy="no-referrer"
          srcDoc={sandboxedDocument(text)}
          tabIndex={-1}
          aria-hidden="true"
          loading="lazy"
        />
        <span className="thumb-badge">
          <Globe size={12} aria-hidden="true" />
          {words.webPage}
        </span>
      </div>
    );
  } else {
    const excerpt = excerptLines(text, CODE_LINES);
    // `highlight` escapes the text and adds only its own span tags.
    const html = kind === "code" ? highlight(excerpt, codeLanguage(item.name)) : null;
    body = html ? (
      <pre className="thumb-pre">
        <code className="hljs" dangerouslySetInnerHTML={{ __html: html }} />
      </pre>
    ) : (
      <pre className="thumb-pre">{excerpt}</pre>
    );
  }

  return (
    <div ref={ref} className={`thumb thumb-text thumb-${kind}`} aria-hidden="true">
      {body}
    </div>
  );
}
