/**
 * The moment a project's crew first exists in this browser: the mark's centre, then each agent
 * taking its seat around it, then "Your crew is ready". It lasts under 1.6 seconds, is skippable
 * (Esc, the close button, a click outside), and under reduced motion it is a still card. It is
 * shown once per project per browser; the page decides when to mount it with `shouldShowAssembled`.
 */
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { X } from "lucide-react";
import { crew } from "../strings.crew";
import { Avatar } from "../ui/Avatar";
import { LogoMark } from "../ui/Logo";
import { roleLine } from "./logic";

const STORAGE_KEY = "crewmind.crew-assembled";
/** Layout only: seats placed around the centre; the rest are counted. */
const RING_MAX = 8;
/** Layout only: above this many seats, roles are left off so names do not collide. */
const ROLES_UP_TO = 6;
/** Timing (ms) of the sequence; the whole moment stays under 1.6 s. */
const SEAT_START = 220;
const SEAT_SPREAD = 720;
const SEAT_STEP_MAX = 110;

export interface AssembledSeat {
  /** The seat name: the identity, and the avatar's colour. */
  name: string;
  /** The name it goes by, shown first (EXE-18). */
  displayName?: string;
  /** The role, short: "CEO". */
  role: string;
  kind: string;
}

interface Props {
  projectId: string;
  seats: AssembledSeat[];
  /** "Meet the crew". */
  onDone(): void;
  /** Esc, the close button or a click outside. Without it, the moment just closes itself. */
  onSkip?(): void;
}

function readSeen(): string[] {
  const value: unknown = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "[]");
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

/** Whether this browser has not yet seen this project's crew assemble. False when storage is unavailable. */
export function shouldShowAssembled(projectId: string): boolean {
  try {
    return !readSeen().includes(projectId);
  } catch {
    return false;
  }
}

/** Remembers that this browser has seen this project's crew assemble. */
export function markAssembled(projectId: string): void {
  try {
    const seen = readSeen();
    if (!seen.includes(projectId)) window.localStorage.setItem(STORAGE_KEY, JSON.stringify([...seen, projectId]));
  } catch {
    // Storage is off or full: the moment may play again, which is harmless.
  }
}

function prefersStill(): boolean {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

/** The CEO at the top, then the others in the order given. */
function inOrder(seats: readonly AssembledSeat[]): AssembledSeat[] {
  return [...seats].sort((a, b) => Number(b.kind === "ceo") - Number(a.kind === "ceo"));
}

export function CrewAssembled({ projectId, seats, onDone, onSkip }: Props): JSX.Element | null {
  const [gone, setGone] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const meet = useRef<HTMLButtonElement>(null);
  const [still] = useState(prefersStill);

  useEffect(() => {
    markAssembled(projectId);
  }, [projectId]);

  useEffect(() => {
    const element = dialog.current;
    if (element && !element.open && typeof element.showModal === "function") element.showModal();
    meet.current?.focus();
  }, []);

  if (gone) return null;

  const finish = (met: boolean): void => {
    setGone(true);
    if (met) onDone();
    else onSkip?.();
  };

  const ordered = inOrder(seats);
  const ring = ordered.slice(0, RING_MAX);
  const step = ring.length > 1 ? Math.min(SEAT_STEP_MAX, SEAT_SPREAD / (ring.length - 1)) : 0;
  const placed = ring.map((seat, index) => {
    const angle = -Math.PI / 2 + (index * 2 * Math.PI) / Math.max(1, ring.length);
    const x = Math.round(Math.cos(angle) * 1000) / 1000;
    const y = Math.round(Math.sin(angle) * 1000) / 1000;
    return { seat, x, y, delay: SEAT_START + index * step };
  });

  return (
    // A click on the backdrop skips, as Esc does (the dialog's cancel event).
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-noninteractive-element-interactions
    <dialog
      ref={dialog}
      className={`assembled${still ? " is-still" : ""}${ring.length > ROLES_UP_TO ? " no-roles" : ""}`}
      aria-labelledby="assembled-title"
      aria-describedby="assembled-line"
      data-testid="crew-assembled"
      onCancel={(event) => {
        event.preventDefault();
        finish(false);
      }}
      onClick={(event) => {
        if (event.target === dialog.current) finish(false);
      }}
    >
      <div className="assembled-card">
        <button type="button" className="button ghost icon-only assembled-close" onClick={() => finish(false)} aria-label={crew.assembled.skip}>
          <X size={18} aria-hidden="true" />
        </button>
        <div className="assembled-stage" aria-hidden="true">
          <svg className="assembled-lines" viewBox="-1 -1 2 2">
            {placed.map(({ seat, x, y, delay }) => (
              <line
                key={seat.name}
                x1={x * 0.3}
                y1={y * 0.3}
                x2={x * 0.72}
                y2={y * 0.72}
                pathLength={1}
                style={{ animationDelay: `${delay + 160}ms` }}
              />
            ))}
          </svg>
          <span className="assembled-centre">
            <LogoMark size={56} />
          </span>
          {placed.map(({ seat, x, y, delay }) => (
            <span
              key={seat.name}
              className={`assembled-seat${y < -0.3 ? " label-above" : ""}${seat.kind === "ceo" ? " is-ceo" : ""}`}
              style={{ "--x": x, "--y": y, animationDelay: `${delay}ms` } as CSSProperties}
            >
              <Avatar name={seat.displayName ?? seat.name} hueKey={seat.name} size="lg" />
              <span className="assembled-label">
                <span className="assembled-name">{seat.displayName ?? seat.name}</span>
                {seat.role.trim().toLowerCase() !== (seat.displayName ?? seat.name).trim().toLowerCase() ? (
                  <span className="assembled-role">{roleLine(seat.displayName ?? seat.name, seat.role)}</span>
                ) : null}
              </span>
            </span>
          ))}
        </div>
        <div className="assembled-text">
          <h2 id="assembled-title">{crew.assembled.title}</h2>
          <p id="assembled-line" className="quiet">
            {crew.assembled.line(seats.length)}
          </p>
          <ul className="visually-hidden">
            {ordered.map((seat) => (
              <li key={seat.name}>
                {seat.displayName ?? seat.name}, {seat.role}
              </li>
            ))}
          </ul>
          <button type="button" ref={meet} className="button primary" onClick={() => finish(true)}>
            {crew.assembled.meet}
          </button>
        </div>
      </div>
    </dialog>
  );
}
