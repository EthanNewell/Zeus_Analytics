/**
 * Кадры сервиса для презентации: снимает блоки страниц статичного демо (имена реальных людей
 * там уже скрыты) в presentation/img. Демо собирается командой export_demo и раздаётся любым
 * статичным сервером:  BASE=http://localhost:8790/kod-prozrachnosti/ node presentation/shots.mjs
 */
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const { chromium } = await import(process.env.PLAYWRIGHT || "playwright");
const base = process.env.BASE || "https://oskarasadullin.github.io/kod-prozrachnosti/";
const AKSAI = "cases/b64101b0-6ae5-45ee-91e3-acb7182f95e2/";
const TAIL = "cases/ef36696f-26a7-4083-bac9-263ad0ac4c45/";

const shots = [
  // [файл, страница, селектор, ширина окна]
  ["findings", AKSAI, ".finding", 1180],
  ["timeline", AKSAI, "ol.timeline", 1408],
  ["outline", TAIL, ".case-head", 1040],
  ["map", "map/", ".map-grid", 1408],
  ["registry", "cases/", "table", 1408],
  ["quality", "method/", ".quality", 1408],
];

const browser = await chromium.launch({ channel: "chrome", headless: true });
for (const [name, path, selector, width] of shots) {
  const page = await browser.newPage({ viewport: { width, height: 900 }, deviceScaleFactor: 2 });
  await page.goto(base + path, { waitUntil: "networkidle" });
  await page.addStyleTag({ content: ":root { --gut: 0px !important; } .hdr, header, .toasts, .case-head a.eyebrow { display: none !important; } * { transition: none !important; }" });
  await page.waitForTimeout(name === "map" ? 5000 : 600);
  const el = await page.$(selector);
  if (!el) { console.log("нет", name, selector); await page.close(); continue; }
  await el.screenshot({ path: resolve(here, "img", `${name}.png`) });
  const box = await el.boundingBox();
  console.log(name, Math.round(box.width), "×", Math.round(box.height));
  await page.close();
}
await browser.close();
