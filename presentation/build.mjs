/**
 * Печать презентации: presentation/deck.html → presentation/kod-prozrachnosti.pdf (1600 × 900,
 * без полей, слайд на страницу). С флагом --png ещё и кадры слайдов в presentation/png для проверки.
 *
 *   PLAYWRIGHT=/путь/к/playwright/index.mjs node presentation/build.mjs [--png]
 */
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, resolve } from "node:path";
import { mkdirSync } from "node:fs";

const here = dirname(fileURLToPath(import.meta.url));
const { chromium } = await import(process.env.PLAYWRIGHT || "playwright");

const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 900 }, deviceScaleFactor: 2 });
await page.goto(pathToFileURL(resolve(here, "deck.html")).href, { waitUntil: "networkidle" });
await page.waitForFunction(() => document.documentElement.dataset.fitted === "1");
if (process.argv.includes("--png")) {
  mkdirSync(resolve(here, "png"), { recursive: true });
  const slides = await page.$$(".slide");
  for (const [i, slide] of slides.entries()) {
    await slide.screenshot({ path: resolve(here, "png", `${String(i + 1).padStart(2, "0")}.png`) });
  }
  // технологическая схема отдельно — для паспорта проекта
  await (await page.$(".flow")).screenshot({ path: resolve(here, "png", "flow.png") });
}
await page.emulateMedia({ media: "print" });
await page.waitForTimeout(800);
await page.pdf({
  path: resolve(here, "kod-prozrachnosti.pdf"),
  width: "1600px", height: "900px", printBackground: true,
  margin: { top: 0, right: 0, bottom: 0, left: 0 },
});
await browser.close();
console.log("готово: presentation/kod-prozrachnosti.pdf");
