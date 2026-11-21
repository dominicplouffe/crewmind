/** Decides how to show a file from its name and media type. Display only. */

export type PreviewKind = "markdown" | "html" | "csv" | "image" | "pdf" | "audio" | "video" | "code" | "text" | "none";

const CODE_LANGUAGES: Record<string, string> = {
  py: "python", js: "javascript", mjs: "javascript", jsx: "javascript", ts: "typescript", tsx: "typescript",
  json: "json", yaml: "yaml", yml: "yaml", toml: "ini", ini: "ini", sh: "bash", bash: "bash", css: "css",
  scss: "scss", sql: "sql", go: "go", rs: "rust", java: "java", kt: "kotlin", c: "c", h: "c", cpp: "cpp",
  cs: "csharp", rb: "ruby", php: "php", swift: "swift", xml: "xml", svgsrc: "xml", diff: "diff", patch: "diff",
  r: "r", lua: "lua", pl: "perl", graphql: "graphql", makefile: "makefile", dockerfile: "bash",
};
const TEXT_EXTENSIONS = new Set(["txt", "log", "text", "rst", "tsv", "env", "cfg", "conf"]);
const IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "avif"]);

export function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot === -1 ? name.toLowerCase() : name.slice(dot + 1).toLowerCase();
}

export function codeLanguage(name: string): string | undefined {
  return CODE_LANGUAGES[extensionOf(name)];
}

export function previewKind(name: string, mediaType: string | null | undefined): PreviewKind {
  const type = (mediaType ?? "").toLowerCase().split(";")[0]?.trim() ?? "";
  const extension = extensionOf(name);
  if (extension === "md" || extension === "markdown" || type === "text/markdown") return "markdown";
  if (extension === "html" || extension === "htm" || type === "text/html") return "html";
  if (extension === "csv" || type === "text/csv") return "csv";
  if (type === "application/pdf" || extension === "pdf") return "pdf";
  if (type.startsWith("image/") || IMAGE_EXTENSIONS.has(extension)) return "image";
  if (type.startsWith("audio/")) return "audio";
  if (type.startsWith("video/")) return "video";
  if (CODE_LANGUAGES[extension]) return "code";
  if (type.startsWith("text/") || TEXT_EXTENSIONS.has(extension)) return "text";
  if (type === "application/json" || type.endsWith("+json") || type.endsWith("+xml")) return "code";
  return "none";
}

export function isTextKind(kind: PreviewKind): boolean {
  return kind === "markdown" || kind === "html" || kind === "csv" || kind === "code" || kind === "text";
}

/**
 * Wraps untrusted HTML for a sandboxed frame. The policy blocks every network request;
 * only inline styles and images embedded in the file itself can load.
 */
export function sandboxedDocument(html: string): string {
  const policy =
    "default-src 'none'; style-src 'unsafe-inline'; img-src data:; media-src data:; font-src data:; " +
    "form-action 'none'; base-uri 'none'";
  return `<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${policy}">${html}`;
}
