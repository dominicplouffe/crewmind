/** Text held to a couple of lines, with "More" when it runs longer. Display only. */
import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  className?: string;
  moreLabel: string;
  lessLabel: string;
  /** Said to screen readers after "More": what opening it shows. */
  moreHint: string;
}

export function Clamp({ children, className = "", moreLabel, lessLabel, moreHint }: Props): JSX.Element {
  const box = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [long, setLong] = useState(false);
  const id = useId();

  const measure = useCallback(() => {
    const element = box.current;
    if (!element || open) return;
    setLong(element.scrollHeight > element.clientHeight + 1);
  }, [open]);

  useEffect(() => {
    measure();
    const element = box.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [measure, children]);

  return (
    <div className={`clamp ${className} ${open ? "is-open" : ""}`}>
      <div ref={box} id={id} className="clamp-text">
        {children}
      </div>
      {long || open ? (
        <button type="button" className="clamp-toggle" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
          {open ? lessLabel : moreLabel}
          {open ? null : <span className="visually-hidden">: {moreHint}</span>}
        </button>
      ) : null}
    </div>
  );
}
