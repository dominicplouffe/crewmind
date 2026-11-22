import { describe, expect, it, vi } from "vitest";
import { ApiError } from "./client";
import { sendChunks, toBase64 } from "./upload";

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

describe("sendChunks", () => {
  it("sends a file in order, chunk by chunk", async () => {
    const file = new Blob([new Uint8Array(250)]);
    const offsets: Array<[number, number]> = [];
    const progress: number[] = [];
    const send = vi.fn(async (_id: string, offset: number, chunk: Blob) => {
      offsets.push([offset, chunk.size]);
      return json(200, { received: offset + chunk.size, size: 250 });
    });
    const end = await sendChunks("u1", file, 0, (received) => progress.push(received), send, 100);
    expect(offsets).toEqual([[0, 100], [100, 100], [200, 50]]);
    expect(progress).toEqual([100, 200, 250]);
    expect(end).toBe(250);
  });

  it("resumes from the server's count after a 409", async () => {
    const file = new Blob([new Uint8Array(300)]);
    const offsets: number[] = [];
    const send = vi.fn(async (_id: string, offset: number, chunk: Blob) => {
      offsets.push(offset);
      if (offsets.length === 2) return json(409, { received: 150, size: 300 });
      return json(200, { received: offset + chunk.size, size: 300 });
    });
    await sendChunks("u1", file, 0, () => {}, send, 100);
    expect(offsets).toEqual([0, 100, 150, 250]);
  });

  it("starts where an earlier attempt stopped", async () => {
    const file = new Blob([new Uint8Array(300)]);
    const offsets: number[] = [];
    await sendChunks("u1", file, 200, () => {}, async (_id, offset, chunk) => {
      offsets.push(offset);
      return json(200, { received: offset + chunk.size });
    }, 100);
    expect(offsets).toEqual([200]);
  });

  it("retries a chunk after a network failure", async () => {
    const file = new Blob([new Uint8Array(100)]);
    let calls = 0;
    await sendChunks("u1", file, 0, () => {}, async (_id, offset, chunk) => {
      calls += 1;
      if (calls === 1) throw new TypeError("network");
      return json(200, { received: offset + chunk.size });
    }, 100);
    expect(calls).toBe(2);
  });

  it("gives up with the server's refusal when it is not a resume", async () => {
    const file = new Blob([new Uint8Array(100)]);
    const send = async (): Promise<Response> =>
      json(413, { kind: "rule", code: "too_large", message: "The file is too large.", rule: "ART-6", hint: "Send a smaller file." });
    const failure = sendChunks("u1", file, 0, () => {}, send, 100);
    await expect(failure).rejects.toBeInstanceOf(ApiError);
    await expect(failure).rejects.toMatchObject({ message: "The file is too large.", hint: "Send a smaller file." });
  });

  it("stops instead of looping when the server keeps answering 409", async () => {
    const file = new Blob([new Uint8Array(100)]);
    const send = vi.fn(async () => json(409, { received: 0, size: 100 }));
    await expect(sendChunks("u1", file, 0, () => {}, send, 100)).rejects.toBeInstanceOf(ApiError);
    expect(send.mock.calls.length).toBeLessThanOrEqual(5);
  });
});

describe("toBase64", () => {
  it("encodes bytes", () => {
    expect(toBase64(new TextEncoder().encode("# Hi\n\ntext"))).toBe("IyBIaQoKdGV4dA==");
  });
});
