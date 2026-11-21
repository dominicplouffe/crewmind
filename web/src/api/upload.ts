/** Sends files to a project: one call for small files, resumable chunks for large ones. */
import { errorFrom, post, type Artifact } from "./client";

/** Files above this size go through the chunked route, as the API asks. */
export const CHUNKED_ABOVE_BYTES = 1024 * 1024;
export const CHUNK_BYTES = 512 * 1024;
const MAX_ATTEMPTS_PER_CHUNK = 5;

export type ChunkSender = (uploadId: string, offset: number, chunk: Blob) => Promise<Response>;

const sendChunk: ChunkSender = (uploadId, offset, chunk) =>
  fetch(`/files/v1/uploads/${encodeURIComponent(uploadId)}?offset=${offset}`, {
    method: "PUT",
    credentials: "same-origin",
    headers: { "content-type": "application/octet-stream" },
    body: chunk,
  });

async function receivedFrom(response: Response): Promise<number | null> {
  try {
    const body = (await response.clone().json()) as { received?: unknown };
    return typeof body.received === "number" ? body.received : null;
  } catch {
    return null;
  }
}

/**
 * Sends `file` in chunks. After each answer it continues from the `received` count the server
 * reports; a 409 means the server stands somewhere else, and its `received` says where.
 */
export async function sendChunks(
  uploadId: string,
  file: Blob,
  startAt: number,
  onProgress: (received: number) => void = () => {},
  send: ChunkSender = sendChunk,
  chunkBytes: number = CHUNK_BYTES,
): Promise<number> {
  let offset = startAt;
  let attempts = 0;
  while (offset < file.size) {
    let response: Response;
    try {
      response = await send(uploadId, offset, file.slice(offset, offset + chunkBytes));
    } catch (error) {
      attempts += 1;
      if (attempts >= MAX_ATTEMPTS_PER_CHUNK) throw error;
      continue;
    }
    const received = await receivedFrom(response);
    if (response.status === 409 && received !== null) {
      attempts += 1;
      if (attempts >= MAX_ATTEMPTS_PER_CHUNK) throw await errorFrom(response);
      offset = received;
      onProgress(offset);
      continue;
    }
    if (!response.ok) throw await errorFrom(response);
    attempts = 0;
    offset = received ?? offset + Math.min(chunkBytes, file.size - offset);
    onProgress(offset);
  }
  return offset;
}

export function toBase64(bytes: Uint8Array): string {
  let binary = "";
  const step = 0x8000;
  for (let i = 0; i < bytes.length; i += step) {
    binary += String.fromCharCode(...bytes.subarray(i, i + step));
  }
  return btoa(binary);
}

/** Uploads one file to the project and returns the stored artifact. */
export async function uploadFile(
  projectId: string,
  file: File,
  onProgress: (fraction: number) => void = () => {},
): Promise<Artifact> {
  const mediaType = file.type || "application/octet-stream";
  if (file.size <= CHUNKED_ABOVE_BYTES) {
    const content = toBase64(new Uint8Array(await file.arrayBuffer()));
    const stored = await post("/v1/artifacts/upload", {
      project_id: projectId,
      name: file.name,
      content_base64: content,
      media_type: mediaType,
    });
    onProgress(1);
    return stored;
  }
  const begun = await post("/v1/uploads/begin", {
    project_id: projectId,
    name: file.name,
    size: file.size,
    media_type: mediaType,
  });
  await sendChunks(begun.upload_id, file, begun.received, (received) => onProgress(received / file.size));
  return post("/v1/uploads/finish", { project_id: projectId, upload_id: begun.upload_id });
}
