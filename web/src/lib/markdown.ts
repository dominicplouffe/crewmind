/** Renders untrusted markdown to safe HTML: parsed, code highlighted, then sanitized. */
import DOMPurify from "dompurify";
import hljs from "highlight.js/lib/common";
import { Marked, type Tokens } from "marked";

function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/** Highlighted HTML for a piece of code. Unknown languages come back escaped and unstyled. */
export function highlight(code: string, language?: string): string {
  if (language && hljs.getLanguage(language)) {
    return hljs.highlight(code, { language, ignoreIllegals: true }).value;
  }
  return escapeHtml(code);
}

const marked = new Marked({
  gfm: true,
  breaks: true,
  renderer: {
    code({ text, lang }: Tokens.Code): string {
      const language = (lang ?? "").trim().split(/\s+/)[0] ?? "";
      const known = language && hljs.getLanguage(language) ? language : "";
      const label = known ? ` data-language="${escapeHtml(known)}"` : "";
      return `<pre tabindex="0"${label}><code class="hljs">${highlight(text, known)}</code></pre>`;
    },
    table(this: { parser: { parseInline(tokens: Tokens.Generic[]): string } }, token: Tokens.Table): string {
      const cell = (c: Tokens.TableCell, tag: "th" | "td"): string =>
        `<${tag}${tag === "th" ? ' scope="col"' : ""}>${this.parser.parseInline(c.tokens)}</${tag}>`;
      const head = token.header.map((c) => cell(c, "th")).join("");
      const rows = token.rows.map((row) => `<tr>${row.map((c) => cell(c, "td")).join("")}</tr>`).join("");
      return `<div class="table-scroll" tabindex="0"><table><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div>`;
    },
  },
});

const purify = DOMPurify(window);

purify.addHook("afterSanitizeAttributes", (node) => {
  if (node.tagName === "A") {
    node.setAttribute("target", "_blank");
    node.setAttribute("rel", "noopener noreferrer nofollow");
  }
  if (node.tagName === "IMG") {
    node.setAttribute("loading", "lazy");
    node.setAttribute("referrerpolicy", "no-referrer");
    if (!node.getAttribute("alt")) node.setAttribute("alt", "");
  }
});

const ALLOWED_TAGS = [
  "a", "b", "blockquote", "br", "code", "del", "details", "div", "em", "h1", "h2", "h3", "h4", "h5", "h6",
  "hr", "i", "img", "input", "li", "ol", "p", "pre", "s", "span", "strong", "sub", "summary", "sup",
  "table", "tbody", "td", "th", "thead", "tr", "ul",
];
const ALLOWED_ATTR = [
  "href", "src", "alt", "title", "class", "scope", "tabindex", "data-language", "start", "type", "checked",
  "disabled", "align",
];

/** Safe HTML for a markdown string. Scripts, event handlers and unknown tags never survive. */
export function renderMarkdown(source: string): string {
  const html = marked.parse(source, { async: false });
  return purify.sanitize(html, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
    ALLOW_DATA_ATTR: false,
    ALLOWED_URI_REGEXP: /^(?:https?:|mailto:|data:image\/(?:png|gif|jpeg|webp);|\/files\/|#)/i,
  });
}
