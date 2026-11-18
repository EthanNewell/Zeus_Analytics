# Пакет для сдачи

Всё собирается из исходников этой папки; готовые файлы в git не лежат.

| Что | Исходник | Сборка |
|---|---|---|
| Презентация PDF, 17 слайдов 1600 × 900, по 10 блокам паспорта | `deck.html` | `node build.mjs --png` |
| Презентация PPTX (картинки слайдов) | `png/` | `python3 to_pptx.py` |
| Кадры сервиса для слайдов | статичное демо | `BASE=… node shots.mjs` |
| Паспорт проекта по типовой форме | шаблон организаторов | `python3 passport.py` |
| Ссылка и инструкция запуска | — | `python3 launch_doc.py` |
| Ролик 2,5 мин, 1920 × 1080 | чистая установка по README | `BASE=… DEMO_USER=head PASS=… node video.mjs`, затем ffmpeg в mp4 |
| Фильм с моушн-дизайном и музыкой, 2:28 | `film/` | см. ниже |

Для node-скриптов нужен Playwright и установленный Chrome (`PLAYWRIGHT=/путь/к/playwright/index.mjs`),
для Python — `python-docx` и `python-pptx`. Поля, которые знает только команда (вуз, ФИО, контакты),
в паспорте и на слайдах стоят в квадратных скобках.

## Фильм

Сцены — `film/film.html` (каждый кадр — функция времени), такты — `film/timeline.json`, общие с музыкой.

1. Чистая запись сервиса: `NOCAP=1 BASE=… DEMO_USER=head PASS=… node video.mjs`, затем
   `video/raw.webm` → `film/footage.webm`, `video/marks.json` → `film/marks.json`.
2. Клипы: `sh film/clips.sh`.
3. Музыка (синтез кодом, без чужих записей): `python3 film/music.py`.
4. Контур участка для сцены «Геометрия»: `python3 film/shape.py`.
5. Рендер и сведение: `node film/render.mjs` → `video/kod-prozrachnosti-film.mp4`;
   отдельные кадры для проверки: `node film/render.mjs --stills 5,48,103`.
