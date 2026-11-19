/**
 * Замер сетки презентации: у каждого слайда тело должно доходить до низа области (без пустот),
 * ничего не вылезает за поля 96 px и за область, шапка одной высоты.
 *
 *   PLAYWRIGHT=… node presentation/audit.mjs
 */
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const { chromium } = await import(process.env.PLAYWRIGHT || "playwright");
const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
await page.goto(pathToFileURL(resolve(here, "deck.html")).href, { waitUntil: "networkidle" });
await page.waitForFunction(() => document.documentElement.dataset.fitted === "1");

const report = await page.evaluate(() => {
  const out = [];
  document.querySelectorAll(".slide").forEach((slide, i) => {
    const s = slide.getBoundingClientRect();
    const problems = [];
    const area = slide.querySelector(".pad > .area, .pad > ol.area");
    // Самый нижний видимый край содержимого внутри области (текст, картинка, линия).
    if (area) {
      const a = area.getBoundingClientRect();
      let bottom = a.top;
      area.querySelectorAll("*").forEach((el) => {
        const r = el.getBoundingClientRect();
        if (!r.width || !r.height) return;
        const st = getComputedStyle(el);
        const visible = el.tagName === "IMG" || el.childNodes.length && [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())
          || st.backgroundColor !== "rgba(0, 0, 0, 0)" || parseFloat(st.borderBottomWidth) > 0;
        if (visible) bottom = Math.max(bottom, r.bottom);
        if (r.bottom > a.bottom + 1) problems.push(`вылезает вниз: ${el.tagName}.${el.className} на ${Math.round(r.bottom - a.bottom)}`);
      });
      const gap = Math.round(a.bottom - bottom);
      if (gap > 12) problems.push(`пустота внизу области ${gap} px`);
      const head = slide.querySelector(".head");
      if (head) out.push({ n: i + 1, headTop: Math.round(head.getBoundingClientRect().top - s.top), areaTop: Math.round(a.top - s.top), areaBottom: Math.round(a.bottom - s.top), problems });
      else out.push({ n: i + 1, problems });
    } else out.push({ n: i + 1, problems: ["нет области (первый экран или разворот)"] });
    slide.querySelectorAll("*").forEach((el) => {
      const r = el.getBoundingClientRect();
      if (!r.width || slide.classList.contains("s-band")) return;
      if (r.right > s.right - 95 || r.left < s.left + 95) {
        if (el.closest(".s-hero") && el.closest(".hero-plate")) return;
        if (el.tagName !== "SECTION" && !el.classList.contains("slide")) problems.push(`за полем: ${el.tagName}.${el.className}`);
      }
    });
    // Текст, вылезающий из своей коробки.
    slide.querySelectorAll("p, span, b, td, th, h1, h2, h3, li").forEach((el) => {
      if (el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).overflow !== "visible") problems.push(`текст шире коробки: ${el.textContent.slice(0, 30)}`);
    });
  });
  return out;
});
for (const r of report) {
  const where = r.areaTop ? ` шапка ${r.headTop}, область ${r.areaTop}–${r.areaBottom}` : "";
  console.log(String(r.n).padStart(2, "0") + where + (r.problems.length ? "\n   " + [...new Set(r.problems)].slice(0, 6).join("\n   ") : "  ок"));
}
await browser.close();
