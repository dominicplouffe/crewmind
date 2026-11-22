// Renders public/icon.svg to the PNG sizes the manifest lists, using the installed Chromium.
import { readFileSync, writeFileSync } from "node:fs";
import { chromium } from "@playwright/test";

const svg = readFileSync(new URL("../public/icon.svg", import.meta.url), "utf8");
const maskable = svg.replace('rx="128"', 'rx="0"');
const browser = await chromium.launch();
for (const [file, size, source] of [
  ["icon-192.png", 192, svg],
  ["icon-512.png", 512, svg],
  ["icon-maskable-512.png", 512, maskable],
]) {
  const page = await browser.newPage({ viewport: { width: size, height: size } });
  await page.setContent(`<style>html,body{margin:0;background:transparent}svg{display:block;width:${size}px;height:${size}px}</style>${source}`);
  writeFileSync(new URL(`../public/${file}`, import.meta.url), await page.screenshot({ omitBackground: true }));
  await page.close();
}
await browser.close();
