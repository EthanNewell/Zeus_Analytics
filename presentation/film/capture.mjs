/**
 * Кадры сервиса для фильма: чёткие снимки страниц вместо видеозаписи экрана.
 * Окно 1280 px, плотность 2× — в фильме страница идёт во всю ширину кадра, текст читается.
 * Камера фильма ездит по снимку целой страницы; положения блоков пишутся в shots/boxes.json.
 *
 *   BASE=http://127.0.0.1:8766 DEMO_USER=head PASS=… PLAYWRIGHT=… node presentation/film/capture.mjs
 *
 * Запускать на чистой установке с demo_data (ФИО инициалами, ИНН скрыты).
 */
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";

const here = dirname(fileURLToPath(import.meta.url));
const { chromium } = await import(process.env.PLAYWRIGHT || "playwright");
const base = process.env.BASE || "http://127.0.0.1:8766";
const out = resolve(here, "shots");
rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });

const W = 1280, H = 720;
const browser = await chromium.launch({ channel: "chrome", headless: true });
const context = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 2 });
// the floating search bar would sit in the middle of every full-page shot, on every page
await context.addInitScript(() => document.addEventListener("DOMContentLoaded", () => {
  const style = document.createElement("style");
  style.textContent = ".search-fab { display: none !important; }";
  document.head.appendChild(style);
}));
const page = await context.newPage();
const boxes = {};

async function go(path) {
  await page.goto(base + path, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(300);
}

// Снимок: целая страница (full) или окно; плюс рамки нужных блоков в координатах страницы.
async function shot(name, { full = true, marks = {} } = {}) {
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(150);
  await page.screenshot({ path: resolve(out, `${name}.png`), fullPage: full, animations: "disabled" });
  const size = await page.evaluate(() => ({ w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight }));
  const found = {};
  for (const [key, sel] of Object.entries(marks)) {
    found[key] = await page.evaluate((sel) => {
      const [css, text] = sel.split("|");
      const el = [...document.querySelectorAll(css)].find((e) => !text || e.textContent.includes(text));
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height };
    }, sel);
    if (!found[key]) console.warn(`нет блока ${name}.${key}: ${sel}`);
  }
  boxes[name] = { w: full ? size.w : W, h: full ? size.h : H, ...found };
}

// 1. Вход: окно до ввода, затем по снимку на каждый набранный знак.
await go("/accounts/login/");
await shot("login", { full: false, marks: { user: "#id_username", pass: "#id_password", submit: "button[type=submit]" } });
let typed = 0;
for (const [sel, value] of [["#id_username", process.env.DEMO_USER || "head"], ["#id_password", process.env.PASS]]) {
  await page.click(sel);
  for (const ch of value) {
    await page.keyboard.type(ch);
    await page.screenshot({ path: resolve(out, `login-${String(++typed).padStart(2, "0")}.png`), animations: "disabled" });
  }
}
boxes.loginTyped = typed;
boxes.loginUser = (process.env.DEMO_USER || "head").length;
await page.click("button[type=submit]");
await page.waitForLoadState("networkidle");

// 2. Обзор.
await go("/");
await shot("overview", { marks: { prio: ".prio" } });

// 3. Загрузка таблицы и паспорт набора.
await go("/imports/");
await page.setInputFiles("#file", resolve(here, "..", "..", "Code", "demo_data", "Тестовые_данные_И3.xlsx"));
await shot("upload", { marks: { form: "form[enctype]", file: "#file", submit: "form[enctype] button[type=submit]" } });
await page.click("form[enctype] button[type=submit]");
await page.waitForLoadState("networkidle");
await page.evaluate(() => document.fonts.ready);
await shot("passport", { marks: { head: "h1" } });

// 4. Реестр с высоким приоритетом.
await go("/cases/?attention=high");
await shot("registry", { marks: { table: "table", row: "a.row-link" } });

// 5. Карточка главного примера.
await go("/cases/?q=61:02:0600010:2843");
await page.locator("a.row-link").first().click();
await page.waitForLoadState("networkidle");
const cardUrl = page.url();
const cardMarks = {
  head: ".obj-cad", i6: ".obj-why|И6 ", i10: ".obj-why|И10", i1: ".obj-why|И1 ", chrono: "section:has(#time-h)", review: "#review",
};
await shot("card", { marks: cardMarks });

// 6. Решение сотрудника: блок #review снимается отдельно на каждом шаге — фильм кладёт его
// поверх снимка карточки в тех же координатах.
const review = page.locator("#review");
let rk = 0;
const rshot = () => review.screenshot({ path: resolve(out, `review-${String(rk++).padStart(2, "0")}.png`), animations: "disabled" });
await rshot();
await page.locator("#review label").filter({ hasText: /^\s*Подтверждено\s*$/ }).first().click();
await rshot();
const note = "Открыты выписка ЕГРН, протокол комиссии и сведения ЕГРЮЛ. Связь по ИНН подтверждена, лицо подписало заключение по ходатайству.";
await page.locator("#review textarea").click();
for (let i = 0; i < note.length; i += 4) {
  await page.keyboard.type(note.slice(i, i + 4));
  await rshot();
}
boxes.reviewSteps = rk;
await page.evaluate(() => document.activeElement.blur());
await shot("review-filled", { marks: { review: "#review", submit: "#review button[type=submit]", choice: "#review label|Подтверждено", text: "#review textarea" } });
await page.locator("#review button[type=submit]").click();
await page.waitForLoadState("networkidle");
await page.goto(cardUrl, { waitUntil: "networkidle" });
await shot("review-saved", { marks: { review: "#review" } });

// 7. Геометрия: участок с «хвостом».
await go("/cases/?q=61:02:0120105:331");
await page.locator("a.row-link").first().click();
await page.waitForLoadState("networkidle");
await page.evaluate(() => document.fonts.ready);
await shot("geometry", { marks: { head: ".obj-cad", i8: ".obj-why|И8", shape: ".outline-plate" } });

// 8. Карта.
await go("/map/");
await page.waitForTimeout(2500);
await shot("map", { full: false, marks: { map: ".map-stage" } });

// 9. Методика и сверка.
await go("/method/");
await shot("method", { marks: { quality: "#quality" } });

await browser.close();
writeFileSync(resolve(out, "boxes.json"), JSON.stringify(boxes, null, 1));
console.log(`готово: ${Object.keys(boxes).length} снимков в presentation/film/shots`);
