/**
 * Кадры сервиса для презентации: снимает блоки страниц статичного демо (имена реальных людей
 * там уже скрыты) в presentation/img. Демо собирается командой export_demo и раздаётся любым
 * статичным сервером:  BASE=http://localhost:8790/kod-prozrachnosti/ AKSAI=<id> TAIL=<id> node presentation/shots.mjs
 * id карточек: manage.py shell -c "from cases.models import Case; print(Case.objects.get(cadastral_number='61:02:0600010:2843').pk)"
 */
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const { chromium } = await import(process.env.PLAYWRIGHT || "playwright");
const base = process.env.BASE || "https://oskarasadullin.github.io/kod-prozrachnosti/";
// Адреса карточек: AKSAI — участок 61:02:0600010:2843, TAIL — 61:02:0120105:331 (id объекта в базе демо).
const AKSAI = `cases/${process.env.AKSAI}/`;
const TAIL = `cases/${process.env.TAIL}/`;
if (!process.env.AKSAI || !process.env.TAIL) throw new Error("задайте AKSAI и TAIL — id карточек в базе демо");

const shots = [
  // [файл, страница, селектор, ширина окна]
  ["findings", AKSAI, ".finding", 1180],
  ["timeline", AKSAI, "ol.timeline", 1408],
  ["outline", TAIL, ".case-head", 1040],
  ["shape", TAIL, ".outline-plate", 1408],
  // карта занимает 80 % высоты окна: при окне 1408 × 652 кадр выходит в пропорции области слайда
  ["map", "map/", ".map-grid", 1408, 652],
  ["registry", "cases/", "table", 1408],
  ["quality", "method/", ".quality", 1408],
];

const browser = await chromium.launch({ channel: "chrome", headless: true });
for (const [name, path, selector, width, height = 900] of shots) {
  const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 2 });
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
