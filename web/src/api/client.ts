/** Typed calls to the crewmind API. Types come from the generated schema; no rules live here. */
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];
export type Message = Schemas["MessageItem"];
export type Header = Schemas["Header"];
export type Card = Schemas["CardItem"];
export type Artifact = Schemas["ArtifactItem"];
export type Project = Schemas["ProjectItem"];
export type Order = Schemas["OrderItem"];
export type Decision = Schemas["DecisionItem"];
export type ReopenRequest = Schemas["RequestItem"];
export type Correction = Schemas["CorrectionItem"];
export type MemoryEntry = Schemas["MemoryItem"];
export type Seat = Schemas["SeatItem"];
export type Task = Schemas["TaskItem"];

type Operation<P extends keyof paths, M extends "get" | "post"> = NonNullable<paths[P][M]>;
type PathsWith<M extends "get" | "post"> = {
  [P in keyof paths]: [Operation<P, M>] extends [never] ? never : P extends `/v1/${string}` ? P : never;
}[keyof paths];

export type GetPath = PathsWith<"get">;
export type PostPath = PathsWith<"post">;

type QueryOf<P extends GetPath> =
  Operation<P, "get"> extends { parameters: { query?: infer Q } } ? (Q extends undefined ? never : Q) : never;
type BodyOf<P extends PostPath> =
  Operation<P, "post"> extends { requestBody: { content: { "application/json": infer B } } } ? B : never;
type ResultOf<P extends keyof paths, M extends "get" | "post"> =
  Operation<P, M> extends { responses: { 200: { content: { "application/json": infer R } } } } ? R : never;

export type GetResult<P extends GetPath> = ResultOf<P, "get">;
export type PostResult<P extends PostPath> = ResultOf<P, "post">;

/** What the server sends when it refuses: shown to the person as given. */
export interface Refusal {
  kind: string;
  code: string;
  message: string;
  rule: string | null;
  hint: string | null;
}

export class ApiError extends Error {
  readonly status: number;
  readonly refusal: Refusal | null;

  constructor(status: number, refusal: Refusal | null, fallback: string) {
    super(refusal?.message ?? fallback);
    this.name = "ApiError";
    this.status = status;
    this.refusal = refusal;
  }

  get hint(): string | null {
    return this.refusal?.hint ?? null;
  }
}

function isRefusal(value: unknown): value is Refusal {
  return typeof value === "object" && value !== null && typeof (value as { message?: unknown }).message === "string";
}

/** Turns a failed response into an ApiError that carries the server's own words. */
export async function errorFrom(response: Response): Promise<ApiError> {
  let refusal: Refusal | null = null;
  try {
    const body: unknown = await response.json();
    if (isRefusal(body)) refusal = body;
  } catch {
    refusal = null;
  }
  return new ApiError(response.status, refusal, `${response.status} ${response.statusText}`.trim());
}

let onSignedOut: (() => void) | null = null;

/** Registers what to do when any call answers 401 (the session ended). */
export function setSignedOutHandler(handler: (() => void) | null): void {
  onSignedOut = handler;
}

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await errorFrom(response);
    if (response.status === 401) onSignedOut?.();
    throw error;
  }
  return (await response.json()) as T;
}

export function queryString(query: object | undefined): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null) params.set(key, String(value));
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

export async function get<P extends GetPath>(
  path: P,
  ...query: [QueryOf<P>] extends [never] ? [] : [QueryOf<P>]
): Promise<GetResult<P>> {
  const response = await fetch(`${path}${queryString(query[0] as object | undefined)}`, {
    credentials: "same-origin",
    headers: { accept: "application/json" },
  });
  return parse<GetResult<P>>(response);
}

export async function post<P extends PostPath>(path: P, body: BodyOf<P>): Promise<PostResult<P>> {
  const response = await fetch(path, {
    method: "POST",
    credentials: "same-origin",
    headers: { "content-type": "application/json", accept: "application/json" },
    body: JSON.stringify(body),
  });
  return parse<PostResult<P>>(response);
}

/** The raw download address of one version of a file. */
export function fileUrl(projectId: string, name: string, version?: number): string {
  const base = `/files/v1/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(name)}`;
  return version === undefined ? base : `${base}?version=${version}`;
}
