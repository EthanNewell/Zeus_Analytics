/**
 * Рендер фильма: film.html → кадры 1920 × 1080, 30 к/с → mp4 со звуком music.wav и дорожкой
 * субтитров (титры сцен из window.SUBTITLES — их читают плееры и автоматическая проверка).
 *
 *   PLAYWRIGHT=… node presentation/film/render.mjs                 # весь фильм
 *   PLAYWRIGHT=… node presentation/film/render.mjs --stills 3,12.5 # отдельные кадры в stills/
 *
 * Кадры снимают четыре вкладки параллельно; каждая вызывает render(t) и ждёт, пока
 * подгрузятся снимки сервиса, поэтому результат не зависит от скорости машины.
 */
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, resolve } from "node:path";
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";

const here = dirname(fileURLToPath(import.meta.url));
const { chromium } = await import(process.env.PLAYWRIGHT || "playwright");
const timeline = JSON.parse(readFileSync(resolve(here, "timeline.json")));
const shape = JSON.parse(readFileSync(resolve(here, "shape.json")));
const boxes = JSON.parse(readFileSync(resolve(here, "shots", "boxes.json")));
const data = { timeline, shape, boxes };

const stillsArg = process.argv.indexOf("--stills");
const stills = stillsArg > 0 ? process.argv[stillsArg + 1].split(",").map(Number) : null;
const outDir = resolve(here, stills ? "stills" : "frames");
rmSync(outDir, { recursive: true, force: true });
mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch({ channel: "chrome", headless: true });
async function tab() {
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  await page.addInitScript((d) => { window.__DATA = d; }, data);
  await page.goto(pathToFileURL(resolve(here, "film.html")).href, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);
  return page;
}

const fps = timeline.fps;
let times;
if (stills) times = stills;
else {
  const end = await (await tab()).evaluate(() => window.FILM_END);
  const total = Math.ceil((end + 4) * fps);
  times = Array.from({ length: total }, (_, i) => i / fps);
}

const workers = stills ? 1 : 4;
const pages = await Promise.all(Array.from({ length: workers }, tab));
let done = 0;
await Promise.all(pages.map(async (page, w) => {
  for (let i = w; i < times.length; i += workers) {
    await page.evaluate((t) => window.render(t), times[i]);
    const name = stills ? `${String(times[i]).replace(".", "_")}.jpg` : `${String(i).padStart(5, "0")}.jpg`;
    await page.screenshot({ path: resolve(outDir, name), type: "jpeg", quality: 93 });
    done++;
    if (!stills && done % 300 === 0) console.log(`${done} / ${times.length}`);
  }
}));
const subs = await pages[0].evaluate(() => window.SUBTITLES);
await browser.close();

if (!stills) {
  const ts = (x) => { const ms = Math.round(x * 1000); const p = (n, w = 2) => String(n).padStart(w, "0");
    return `${p(Math.floor(ms / 3600000))}:${p(Math.floor(ms / 60000) % 60)}:${p(Math.floor(ms / 1000) % 60)},${p(ms % 1000, 3)}`; };
  const srt = resolve(here, "subs.srt");
  writeFileSync(srt, subs.map((s, i) => `${i + 1}\n${ts(s.from)} --> ${ts(s.to)}\n${s.text}\n`).join("\n"));
  const mp4 = resolve(here, "..", "video", "kod-prozrachnosti-film.mp4");
  mkdirSync(dirname(mp4), { recursive: true });
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-framerate", String(fps), "-i", resolve(outDir, "%05d.jpg"),
    "-i", resolve(here, "music.wav"), "-i", srt, "-map", "0:v", "-map", "1:a", "-map", "2:s", "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "256k", "-c:s", "mov_text", "-metadata:s:s:0", "language=rus", "-shortest", "-movflags", "+faststart", mp4]);
  console.log("готово: presentation/video/kod-prozrachnosti-film.mp4");
} else console.log(`кадры: ${outDir}`);
