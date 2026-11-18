/**
 * Ролик с демонстрацией ключевого сценария: вход → данные → анализ → реестр → карточка →
 * решение сотрудника → геометрия и карта → сверка. Записывает Playwright (1920 × 1080),
 * подписи — плашкой внизу кадра. Запускать на чистой установке по README (данные demo_data).
 *
 *   BASE=http://localhost:8000 DEMO_USER=head PASS=… PLAYWRIGHT=… node presentation/video.mjs
 *   → presentation/video/raw.webm, дальше ffmpeg в mp4
 */
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { mkdirSync, readdirSync, renameSync, rmSync } from "node:fs";

const here = dirname(fileURLToPath(import.meta.url));
const { chromium } = await import(process.env.PLAYWRIGHT || "playwright");
const base = process.env.BASE || "http://localhost:8000";
const out = resolve(here, "video");
rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });

const size = { width: 1920, height: 1080 };
const browser = await chromium.launch({ channel: "chrome", headless: true });
const context = await browser.newContext({ viewport: size, recordVideo: { dir: out, size } });
const page = await context.newPage();
const wait = (ms) => page.waitForTimeout(ms);

// Подпись — синяя плашка снизу, тем же шрифтом, что сайт.
async function caption(step, text) {
  await page.evaluate(([step, text]) => {
    let box = document.getElementById("__cap");
    if (!box) {
      box = document.createElement("div");
      box.id = "__cap";
      box.style.cssText = "position:fixed;right:48px;bottom:40px;z-index:99999;max-width:1100px;background:#0000e8;color:#fff;" +
        "padding:22px 28px;display:grid;gap:8px;font-family:'Science Gothic',Arial,sans-serif;font-stretch:72%;pointer-events:none;";
      document.body.appendChild(box);
    }
    box.innerHTML = `<span style="font-weight:400;font-size:14px;letter-spacing:.2em;text-transform:uppercase">${step}</span>` +
      `<span style="font-weight:250;font-size:26px;line-height:1.35">${text}</span>`;
  }, [step, text]);
}

async function scroll(total, steps = 40, pause = 30) {
  for (let i = 0; i < steps; i++) {
    await page.evaluate((dy) => window.scrollBy(0, dy), total / steps);
    await wait(pause);
  }
}

// Плавно подвести блок под шапку сайта.
async function reach(selector) {
  const dy = await page.evaluate((sel) => {
    const el = document.querySelector(sel);
    return el ? el.getBoundingClientRect().top - 96 : 0;
  }, selector);
  await scroll(dy);
}

async function go(path) {
  await page.goto(base + path, { waitUntil: "networkidle" });
  await wait(400);
}

// 1. Вход
await go("/accounts/login/");
await caption("Код прозрачности / Риски в кадастре", "Рабочее место специалиста по профилактике коррупции. Вход по ролям: специалист, проверяющий, руководитель.");
await wait(3500);
await page.fill("#id_username", process.env.DEMO_USER || "head");
await wait(300);
await page.fill("#id_password", process.env.PASS);
await wait(500);
await page.click("button[type=submit]");
await page.waitForLoadState("networkidle");

// 2. Обзор
await caption("01 / обзор", "Сводка по семи правилам исследования и очередь: сначала объекты с высоким приоритетом.");
await wait(4000);
await scroll(900);
await wait(2500);
await scroll(900);
await wait(2500);

// 3. Загрузка
await go("/imports/");
await caption("02 / данные", "Таблицы исследования загружаются как есть, Excel или CSV. Файл проверяется целиком, повторная загрузка не дублирует записи.");
await wait(3500);
await page.setInputFiles("#file", resolve(here, "..", "Code", "demo_data", "Тестовые_данные_И3.xlsx"));
await wait(1500);
await page.click("form[enctype] button[type=submit]");
await page.waitForLoadState("networkidle");
await wait(800);
await caption("02 / данные", "Паспорт набора: источники из примечаний таблицы, реальные и синтетические ячейки посчитаны отдельно.");
await wait(4000);
await scroll(700);
await wait(3000);

// 4. Анализ
await go("/");
await caption("03 / анализ", "Проверяющий запускает анализ: 7 правил по всем 70 записям. Запуск сохраняется и не перезаписывается.");
await wait(2500);
const run = page.locator("form[action*='analysis'] button[type=submit]").first();
if (await run.count()) {
  await run.click();
  await page.waitForLoadState("networkidle");
  await caption("03 / анализ", "Анализ выполнен. Одинаковый вход — одинаковый результат.");
  await wait(3500);
}

// 5. Реестр
await go("/cases/?attention=high");
await caption("04 / реестр", "Реестр с фильтром «высокий приоритет». Процента коррупции нет намеренно: пять уровней приоритета и четыре статуса правила.");
await wait(3000);
await reach("table");
await wait(4000);
await scroll(500);
await wait(2500);

// 6. Карточка: главный пример
await go("/cases/?q=61:02:0600010:2843");
await page.locator("a.row-link").first().click();
await page.waitForLoadState("networkidle");
await caption("05 / карточка", "Аксайский район, 61:02:0600010:2843. Почему объект в реестре — по каждому правилу отдельно.");
await wait(4500);
await scroll(700);
await caption("05 / карточка / И6", "Участок куплен за 75 дней до начала процедуры. Участник решения был учредителем фирмы-покупателя: связь — по ИНН в ЕГРЮЛ.");
await wait(5500);
await scroll(700);
await caption("05 / карточка / И10, И1", "То же лицо — ещё в пяти эпизодах. Категорию сменили через 271 день после покупки.");
await wait(5000);
await scroll(1100);
await caption("05 / карточка / хронология", "Порядок событий система собрала сама из трёх разных таблиц.");
await wait(5000);
await scroll(900);
await caption("05 / карточка / участники", "Участники, основания и документы. К объекту можно приложить файл или ссылку.");
await wait(4500);

// 7. Решение человека
const review = page.locator("#review");
await reach("#review");
await caption("06 / решение человека", "Решение принимает сотрудник. Запись хранится отдельно: факты и сигнал системы не меняются.");
await wait(3000);
await page.locator("#review label", { hasText: "подтверждены" }).first().click();
await wait(800);
await page.locator("#review textarea").click();
await page.keyboard.type("Открыты выписка ЕГРН, протокол комиссии и сведения ЕГРЮЛ. Связь по ИНН подтверждена, нужен запрос документов об участии в решении.", { delay: 18 });
await wait(800);
await page.locator("#review button[type=submit]").click();
await page.waitForLoadState("networkidle");
await page.locator("#review").scrollIntoViewIfNeeded();
await caption("06 / решение человека", "Запись в истории проверки — с автором и временем.");
await wait(4500);
await scroll(1200);
await caption("05 / карточка / исходные факты", "Каждое поле — с ячейкой Excel и происхождением: реальное, синтетическое или вычисленное.");
await wait(5000);

// 8. Геометрия и карта
await go("/cases/?q=61:02:0120105:331");
await page.locator("a.row-link").first().click();
await page.waitForLoadState("networkidle");
await caption("07 / геометрия", "Контур с «хвостом» к реке. Коэффициент заполнения 0,593 считается по координатам, порог — 0,85.");
await wait(5500);
await scroll(700);
await wait(3500);
await go("/map/");
await reach(".map-grid");
await wait(3500);
await caption("07 / карта", "Контуры участков и изменённых зон. Чем плотнее заливка, тем выше приоритет; клик открывает карточку.");
await wait(5500);

// 9. Сверка
await go("/method/");
await caption("08 / методика", "Условия, пороги и ограничения каждого правила — на одной странице.");
await wait(3500);
const quality = page.locator(".quality").first();
if (await quality.count()) await reach(".quality");
await caption("08 / проверка качества", "69 из 70 совпали с разметкой исследования. Расхождение намеренное: совпала только фамилия — это гипотеза, а не связь.");
await wait(6500);

// 10. Финал
await go("/");
await caption("Код прозрачности / Zeus Analytics", "Индикатор — повод проверить, а не вывод о нарушении. Репозиторий: github.com/EthanNewell/Zeus_Analytics");
await wait(5000);

await context.close();
await browser.close();
const file = readdirSync(out).find((name) => name.endsWith(".webm"));
renameSync(resolve(out, file), resolve(out, "raw.webm"));
console.log("готово: presentation/video/raw.webm");
