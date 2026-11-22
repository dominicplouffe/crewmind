/** The message box (CHAT-4): markdown, slash and @ completion, attachments, history, Esc to interrupt. */
import { ArrowUp, CornerUpLeft, File as FileIcon, History, Paperclip, Square, X } from "lucide-react";
import { forwardRef, useEffect, useId, useImperativeHandle, useMemo, useRef, useState } from "react";
import type { Message } from "../api/client";
import { applyCompletion, findCompletion, type Completion, type CompletionOption, type MentionTarget } from "../lib/autocomplete";
import { t } from "../strings";
import { snippet } from "./MessageItem";
import type { UploadItem } from "./useUploads";

export interface ComposerHandle {
  focus(): void;
  insert(text: string): void;
}

interface Props {
  commands: Record<string, string>;
  mentions: MentionTarget[];
  /** Earlier messages from this person, oldest first, for Up-arrow recall. */
  history: string[];
  replyTo: Message | null;
  replying: boolean;
  uploads: UploadItem[];
  onSend(body: string): void;
  onCancelReply(): void;
  onInterrupt(): void;
  onFiles(files: File[]): void;
  onDismissUpload(key: string): void;
}

export const Composer = forwardRef<ComposerHandle, Props>(function Composer(props, ref) {
  const { commands, mentions, history, replyTo, replying, uploads } = props;
  const [text, setText] = useState("");
  const [cursor, setCursor] = useState(0);
  const [active, setActive] = useState(0);
  const [closed, setClosed] = useState(false);
  const [recall, setRecall] = useState<number | null>(null);
  const area = useRef<HTMLTextAreaElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  const listId = useId();
  const hintId = useId();

  const completion: Completion | null = useMemo(
    () => (closed ? null : findCompletion(text, cursor, commands, mentions)),
    [closed, text, cursor, commands, mentions],
  );
  const options = completion?.options ?? [];
  const activeIndex = Math.min(active, Math.max(0, options.length - 1));

  const place = (value: string, at: number): void => {
    setText(value);
    setCursor(at);
    requestAnimationFrame(() => {
      area.current?.focus();
      area.current?.setSelectionRange(at, at);
    });
  };

  useImperativeHandle(ref, () => ({
    focus: () => area.current?.focus(),
    insert: (value: string) => place(value, value.length),
  }));

  useEffect(() => {
    const element = area.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, 240)}px`;
  }, [text]);

  const choose = (option: CompletionOption): void => {
    if (!completion) return;
    const next = applyCompletion(text, completion, option);
    place(next.text, next.cursor);
    setActive(0);
  };

  const send = (): void => {
    const body = text.trim();
    if (!body) return;
    props.onSend(body);
    setText("");
    setCursor(0);
    setRecall(null);
  };

  const recallStep = (step: -1 | 1): boolean => {
    if (history.length === 0) return false;
    const from = recall ?? history.length;
    const index = from + step;
    if (index < 0) return true;
    if (index >= history.length) {
      setRecall(null);
      place("", 0);
      return true;
    }
    setRecall(index);
    const value = history[index] ?? "";
    place(value, value.length);
    return true;
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>): void => {
    if (event.nativeEvent.isComposing) return;
    if (completion && options.length > 0) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const step = event.key === "ArrowDown" ? 1 : -1;
        setActive((activeIndex + step + options.length) % options.length);
        return;
      }
      const exact = options.length === 1 && options[0]?.value === text.slice(completion.start, completion.end);
      if (event.key === "Tab" || (event.key === "Enter" && !event.shiftKey && !exact)) {
        const option = options[activeIndex];
        if (option) {
          event.preventDefault();
          choose(option);
          return;
        }
      }
      if (event.key === "Escape") {
        event.preventDefault();
        setClosed(true);
        return;
      }
    }
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      send();
    } else if (event.key === "Escape") {
      if (replying) props.onInterrupt();
      else if (replyTo) props.onCancelReply();
    } else if (event.key === "ArrowUp" && (text === "" || recall !== null)) {
      if (recallStep(-1)) event.preventDefault();
    } else if (event.key === "ArrowDown" && recall !== null) {
      if (recallStep(1)) event.preventDefault();
    }
  };

  const onPaste = (event: React.ClipboardEvent<HTMLTextAreaElement>): void => {
    const files = Array.from(event.clipboardData.files);
    if (files.length > 0) {
      event.preventDefault();
      props.onFiles(files);
    }
  };

  const last = history[history.length - 1];

  return (
    <form
      className="composer"
      aria-label={t.composer.formLabel}
      onSubmit={(event) => {
        event.preventDefault();
        send();
      }}
    >
      <div className="composer-inner">
        {replyTo ? (
          <div className="replying">
            <CornerUpLeft size={14} aria-hidden="true" />
            <span className="replying-text">
              {t.chat.inReplyTo(replyTo.author)} <q>{snippet(replyTo.body)}</q>
            </span>
            <button
              type="button"
              className="button small ghost icon-only"
              onClick={props.onCancelReply}
              title={t.composer.cancelReply}
            >
              <X size={14} aria-hidden="true" />
              <span className="visually-hidden">{t.composer.cancelReply}</span>
            </button>
          </div>
        ) : null}
        {uploads.length > 0 ? (
          <ul className="uploads plain" aria-label={t.composer.uploadsLabel}>
            {uploads.map((upload) => (
              <li key={upload.key} className={upload.error ? "upload failed" : upload.done ? "upload done" : "upload"}>
                <FileIcon size={14} aria-hidden="true" />
                <span className="upload-name">{upload.name}</span>
                {upload.error ? (
                  <span role="alert">
                    {upload.error.message} {upload.error.hint ?? ""}
                  </span>
                ) : upload.done ? (
                  <span role="status">{t.composer.uploaded}</span>
                ) : (
                  <progress max={1} value={upload.progress} aria-label={t.composer.uploading(upload.name)} />
                )}
                {upload.done || upload.error ? (
                  <button
                    type="button"
                    className="button small ghost icon-only"
                    onClick={() => props.onDismissUpload(upload.key)}
                    title={t.common.dismiss}
                  >
                    <X size={14} aria-hidden="true" />
                    <span className="visually-hidden">
                      {t.common.dismiss} {upload.name}
                    </span>
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        ) : null}
        {completion && options.length > 0 ? (
          <ul className="completions" role="listbox" id={listId} aria-label={t.composer.suggestions[completion.kind]}>
            {options.map((option, index) => (
              // Keyboard use goes through the text box (arrows, Enter, Tab); the click is a pointer shortcut.
              // eslint-disable-next-line jsx-a11y/click-events-have-key-events
              <li
                key={option.value}
                id={`${listId}-${index}`}
                role="option"
                aria-selected={index === activeIndex}
                className={index === activeIndex ? "active" : ""}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => choose(option)}
              >
                <span className="completion-value">{option.value}</span>
                <span className="quiet">{option.detail}</span>
              </li>
            ))}
          </ul>
        ) : null}
        <div className="composer-box">
          <label htmlFor={`${listId}-area`} className="visually-hidden">
            {t.composer.label}
          </label>
          <textarea
            id={`${listId}-area`}
            ref={area}
            rows={1}
            value={text}
            placeholder={t.composer.placeholder}
            aria-describedby={hintId}
            aria-autocomplete="list"
            aria-controls={completion && options.length > 0 ? listId : undefined}
            aria-activedescendant={completion && options.length > 0 ? `${listId}-${activeIndex}` : undefined}
            onChange={(event) => {
              setText(event.target.value);
              setCursor(event.target.selectionStart);
              setClosed(false);
              setActive(0);
              if (recall !== null && event.target.value === "") setRecall(null);
            }}
            onSelect={(event) => setCursor(event.currentTarget.selectionStart)}
            onKeyDown={onKeyDown}
            onPaste={onPaste}
          />
          <div className="composer-row">
            <input
              ref={picker}
              type="file"
              multiple
              className="visually-hidden"
              tabIndex={-1}
              aria-label={t.composer.pickerLabel}
              data-testid="file-picker"
              onChange={(event) => {
                props.onFiles(Array.from(event.target.files ?? []));
                event.target.value = "";
              }}
            />
            <button
              type="button"
              className="button ghost icon-only composer-tool"
              onClick={() => picker.current?.click()}
              title={t.composer.attach}
            >
              <Paperclip size={18} aria-hidden="true" />
              <span className="visually-hidden">{t.composer.attach}</span>
            </button>
            <button
              type="button"
              className="button ghost icon-only composer-tool"
              disabled={!last}
              title={t.composer.editLast}
              onClick={() => {
                if (last) place(last, last.length);
              }}
            >
              <History size={18} aria-hidden="true" />
              <span className="visually-hidden">{t.composer.editLast}</span>
            </button>
            <span className="spacer" />
            {replying ? (
              <button type="button" className="button small composer-stop" onClick={props.onInterrupt}>
                <Square size={12} aria-hidden="true" />
                {t.composer.interrupt}
              </button>
            ) : null}
            <button
              type="submit"
              className="button primary icon-only composer-send"
              disabled={text.trim() === ""}
              title={t.composer.send}
            >
              <ArrowUp size={18} aria-hidden="true" />
              <span className="visually-hidden">{t.composer.send}</span>
            </button>
          </div>
        </div>
        <p className="composer-hint" id={hintId}>
          {t.composer.hint}
        </p>
      </div>
    </form>
  );
});
