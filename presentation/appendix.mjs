/**
 * Печать приложений: presentation/appendix.html → presentation/Приложения_Zeus_Analytics.pdf (A4, книжная).
 * Раздел «Описание набора данных» подставляется из Code/docs/dataset.md, раздел «Текст ролика» —
 * из film/subs.srt. Если файла субтитров нет, раздел и его строка в оглавлении убираются.
 *
 *   PLAYWRIGHT=/путь/к/playwright/index.mjs node presentation/appendix.mjs
 */
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, resolve } from "node:path";
import { existsSync, readFileSync } from "node:fs";

const here = dirname(fileURLToPath(import.meta.url));
const { chromium } = await import(process.env.PLAYWRIGHT || "playwright");

const esc = (text) => text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const inline = (text) =>
  esc(text).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
const cells = (line) => line.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());

/** Markdown описания набора → HTML: заголовки, абзацы, списки, таблицы. Заголовок «#» пропускается. */
function markdown(source) {
  const lines = source.split("\n");
  const out = [];
  for (let i = 0; i < lines.length; ) {
    const line = lines[i];
    if (!line.trim() || line.startsWith("# ")) { i += 1; continue; }
    if (line.startsWith("## ")) { out.push(`<h3>${inline(line.slice(3))}</h3>`); i += 1; continue; }
    if (line.startsWith("|")) {
      const rows = [];
      while (i < lines.length && lines[i].startsWith("|")) rows.push(cells(lines[i++]));
      const [head, , ...body] = rows;
      const numeric = (cell) => /^[\d\s,.]+$/.test(cell);
      out.push(
        `<table${body.at(-1)?.[0] === "Всего" ? ' class="sum"' : ""}><thead><tr>${head.map((c) => `<th>${inline(c)}</th>`).join("")}</tr></thead><tbody>` +
          body.map((row) => `<tr>${row.map((c) => `<td${numeric(c) ? ' class="n"' : ""}>${inline(c)}</td>`).join("")}</tr>`).join("") +
          "</tbody></table>",
      );
      continue;
    }
    if (line.startsWith("- ")) {
      const items = [];
      while (i < lines.length && lines[i].startsWith("- ")) items.push(`<li>${inline(lines[i++].slice(2))}</li>`);
      out.push(`<ul>${items.join("")}</ul>`);
      continue;
    }
    const text = [];
    while (i < lines.length && lines[i].trim() && !/^(#|\||- )/.test(lines[i])) text.push(lines[i++]);
    out.push(`<p>${inline(text.join(" "))}</p>`);
  }
  return out.join("\n");
}

/** Субтитры .srt → таблица «время — текст». */
function subtitles(source) {
  const short = (stamp) => stamp.replace(/^00:/, "").replace(/[,.]\d+$/, "");
  const rows = source.replace(/\r/g, "").replace(/^﻿/, "").split(/\n{2,}/).flatMap((block) => {
    const lines = block.trim().split("\n");
    const at = lines.findIndex((line) => line.includes("-->"));
    if (at < 0) return [];
    const [from, to] = lines[at].split("-->").map((stamp) => short(stamp.trim().split(" ")[0]));
    const text = lines.slice(at + 1).join(" ").replace(/<[^>]+>/g, "").trim();
    return text ? [`<tr><td class="n">${from} – ${to}</td><td>${esc(text)}</td></tr>`] : [];
  });
  if (!rows.length) return "";
  return `<table><thead><tr><th>Время</th><th>Текст</th></tr></thead><tbody>${rows.join("")}</tbody></table>`;
}

const dataset = markdown(readFileSync(resolve(here, "../Code/docs/dataset.md"), "utf8"));
const srt = resolve(here, "film/subs.srt");
const subs = existsSync(srt) ? subtitles(readFileSync(srt, "utf8")) : "";

const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 794, height: 1123 } });
await page.goto(pathToFileURL(resolve(here, "appendix.html")).href, { waitUntil: "networkidle" });
await page.evaluate(({ dataset, subs }) => {
  document.getElementById("dataset").innerHTML = dataset;
  if (subs) document.getElementById("subs").innerHTML = subs;
  else document.querySelectorAll('[data-if="subs"]').forEach((node) => node.remove());
}, { dataset, subs });
await page.evaluate(() => document.fonts.ready);
await page.emulateMedia({ media: "print" });
await page.waitForTimeout(500);
const out = resolve(here, "Приложения_Zeus_Analytics.pdf");
await page.pdf({ path: out, format: "A4", printBackground: true, preferCSSPageSize: true });
await browser.close();
console.log(`готово: presentation/Приложения_Zeus_Analytics.pdf${subs ? "" : " (без раздела «Текст ролика»: нет film/subs.srt)"}`);
