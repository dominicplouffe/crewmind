/** A one-time link shown in a read-only field with a Copy button that says when it worked. */
import { useEffect, useId, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";
import { settingsWords } from "../strings.settings";

export function CopyLink({ link, label }: { link: string; label: string }): JSX.Element {
  const words = settingsWords.common;
  const id = useId();
  const field = useRef<HTMLInputElement>(null);
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");

  useEffect(() => {
    if (state !== "copied") return;
    const timer = window.setTimeout(() => setState("idle"), 2500);
    return () => window.clearTimeout(timer);
  }, [state]);

  const copy = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(link);
      setState("copied");
    } catch {
      field.current?.select();
      setState("failed");
    }
  };

  return (
    <div className="copy-link">
      <label htmlFor={id} className="visually-hidden">
        {label}
      </label>
      <div className="copy-link-row">
        <input id={id} ref={field} readOnly value={link} spellCheck={false} onFocus={(event) => event.currentTarget.select()} />
        <button type="button" className="button" onClick={() => void copy()}>
          {state === "copied" ? <Check size={16} aria-hidden="true" /> : <Copy size={16} aria-hidden="true" />}
          {state === "copied" ? words.copied : words.copy}
        </button>
      </div>
      <p className="visually-hidden" role="status">
        {state === "copied" ? words.copied : ""}
      </p>
      {state === "failed" ? <p className="setting-error">{words.copyFailed}</p> : null}
    </div>
  );
}
