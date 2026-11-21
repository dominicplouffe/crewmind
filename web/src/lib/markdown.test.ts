import { describe, expect, it } from "vitest";
import { sandboxedDocument } from "./files";
import { renderMarkdown } from "./markdown";

function dom(source: string): HTMLDivElement {
  const holder = document.createElement("div");
  holder.innerHTML = renderMarkdown(source);
  return holder;
}

describe("renderMarkdown is safe for untrusted text", () => {
  it("removes script tags", () => {
    const html = renderMarkdown('Hello <script>window.hacked = true</script> **world**');
    expect(html).not.toMatch(/<script/i);
    expect(html).not.toContain("window.hacked");
    expect(html).toContain("<strong>world</strong>");
  });

  it("removes event handler attributes such as onerror", () => {
    const holder = dom('<img src="x" onerror="window.hacked = true"> and <a href="#" onclick="steal()">link</a>');
    expect(holder.innerHTML).not.toMatch(/onerror|onclick/i);
    for (const element of holder.querySelectorAll("*")) {
      for (const attribute of element.attributes) expect(attribute.name.startsWith("on")).toBe(false);
    }
  });

  it("does not run anything when the result is put in the page", () => {
    const marker = window as unknown as { hacked?: boolean };
    marker.hacked = false;
    const holder = dom('<img src="x" onerror="window.hacked = true"><script>window.hacked = true</script><svg onload="window.hacked = true"></svg>');
    document.body.append(holder);
    expect(marker.hacked).toBe(false);
    expect(holder.querySelector("script, svg")).toBeNull();
    holder.remove();
  });

  it("drops javascript: links, iframes, forms and inline styles", () => {
    const holder = dom('[click](javascript:alert(1)) <iframe src="https://example.com"></iframe> <form action="/v1/auth/logout"><button>go</button></form> <p style="position:fixed">x</p>');
    expect(holder.innerHTML).not.toMatch(/javascript:/i);
    expect(holder.querySelector("iframe, form, button, [style]")).toBeNull();
  });

  it("opens links in a new tab without handing over the opener", () => {
    const link = dom("[site](https://example.com)").querySelector("a");
    expect(link?.getAttribute("href")).toBe("https://example.com");
    expect(link?.getAttribute("target")).toBe("_blank");
    expect(link?.getAttribute("rel")).toContain("noopener");
  });

  it("renders highlighted code, tables and images", () => {
    const holder = dom("```python\nprint(1)\n```\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n![chart](https://example.com/chart.png)");
    expect(holder.querySelector("pre code.hljs")?.textContent).toContain("print(1)");
    expect(holder.querySelector("pre code .hljs-built_in, pre code .hljs-number")).not.toBeNull();
    expect(holder.querySelectorAll("table th")).toHaveLength(2);
    expect(holder.querySelector("img")?.getAttribute("alt")).toBe("chart");
  });

  it("escapes HTML inside code blocks", () => {
    const holder = dom("```\n<script>alert(1)</script>\n```");
    expect(holder.querySelector("script")).toBeNull();
    expect(holder.querySelector("pre")?.textContent).toContain("<script>alert(1)</script>");
  });
});

describe("sandboxedDocument", () => {
  it("puts a policy that blocks all network before the untrusted HTML", () => {
    const html = sandboxedDocument('<img src="https://example.com/x.png">');
    expect(html.indexOf("Content-Security-Policy")).toBeLessThan(html.indexOf("<img"));
    expect(html).toContain("default-src 'none'");
    expect(html).not.toMatch(/script-src|connect-src|https?:\/\/[^e]/);
  });
});
