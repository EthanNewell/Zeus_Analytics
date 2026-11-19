"""Документ со ссылкой на репозиторий и инструкцией запуска (пункт 4 пакета сдачи).

    python3 presentation/launch_doc.py   # нужен python-docx
"""

from pathlib import Path

import docx
from docx.shared import Pt, RGBColor

HERE = Path(__file__).parent
OUT = HERE / "Ссылка_и_инструкция_запуска.docx"
REPO = "https://github.com/EthanNewell/Zeus_Analytics"
DEMO = "https://oskarasadullin.github.io/kod-prozrachnosti/"
CI_RUN = "https://github.com/EthanNewell/Zeus_Analytics/actions/runs/44451194428"

VERSIONS = [
    ("Python", "3.12"),
    ("Django", "5.2.19 LTS"),
    ("MySQL", "8.4 (основная база); SQLite — только для локальной проверки"),
    ("Docker Engine / Desktop", "с Docker Compose v2 (флаг --wait)"),
    ("Python-зависимости", "закреплены в Code/requirements.txt (Django, openpyxl, whitenoise, gunicorn и др.), "
     "драйвер MySQL — в requirements-mysql.txt, проверки — в requirements-dev.txt"),
    ("Браузер", "любой современный; карта — OpenLayers 10.11 в составе репозитория, подложка 2ГИС загружается "
     "из интернета"),
]

DOCKER = [
    f"git clone -b oskar/mvp {REPO}.git",
    "cd Zeus_Analytics/Code",
    "cp .env.example .env",
    "docker compose up -d --build --wait",
    "docker compose exec web python manage.py migrate",
    "docker compose exec web python manage.py bootstrap_roles",
    "docker compose exec web python manage.py demo_users",
    "docker compose exec web python manage.py load_tables demo_data --user head",
]

LOCAL = [
    f"git clone -b oskar/mvp {REPO}.git",
    "cd Zeus_Analytics/Code",
    "python3.12 -m venv .venv && source .venv/bin/activate",
    "python -m pip install -r requirements-dev.txt",
    "export DB_ENGINE=sqlite DJANGO_SETTINGS_MODULE=config.settings.local",
    "python manage.py migrate",
    "python manage.py bootstrap_roles",
    "python manage.py demo_users",
    "python manage.py load_tables demo_data --user head",
    "python manage.py runserver 127.0.0.1:8000",
]

CHECKS = [
    "python manage.py test --settings=config.settings.test",
    "curl http://localhost:8000/health/ready/",
]

SCENARIO = [
    "Войдите под head (пароль напечатала команда demo_users).",
    "«Загрузка» — история загрузок семи таблиц, паспорт набора, реальные и синтетические ячейки.",
    "«Обзор» → «Запустить анализ»; итог: 70 записей, 31 сигнал, совпадение с разметкой 69 из 70.",
    "«Реестр» → фильтр «Высокий» → объект 61:02:0600010:2843 (Аксайский район, демонстрационный пример): основания И6, И10, И1, "
    "хронология, исходные факты; внизу страницы запишите проверку сотрудника.",
    "Объект 61:02:0120105:331 — контур с узким выступом (И8), кнопка «Показать на карте».",
    "«Методика» — условия и пороги правил, сверка с разметкой исследования.",
]


def mono(paragraph, text):
    run = paragraph.add_run(text)
    run.font.name = "Courier New"
    run.font.size = Pt(9.5)
    return run


def code_block(d, lines):
    """One paragraph per command, so each stays on its own line in any text export."""
    for i, line in enumerate(lines):
        p = d.add_paragraph()
        p.paragraph_format.space_after = Pt(8 if i == len(lines) - 1 else 0)
        mono(p, line)


def main():
    d = docx.Document()
    style = d.styles["Normal"]
    style.font.name = "Arial"
    style.font.size = Pt(10.5)

    d.add_heading("Код прозрачности — ссылка на прототип и инструкция запуска", level=1)
    d.add_paragraph("Проект «Риски в кадастре» — рабочее место специалиста по профилактике коррупции "
                    "в земельных отношениях. Команда Zeus Analytics. "
                    "Репозиторий и демо принадлежат одной команде, код — в ветке oskar/mvp.")

    d.add_heading("Ссылки", level=2)
    table = d.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    for label, value in [
        ("Репозиторий (открытый), код в ветке oskar/mvp", REPO + "/tree/oskar/mvp"),
        ("Ветка с кодом", "oskar/mvp — команды ниже клонируют эту ветку"),
        ("Инструкция в репозитории", "Code/README.md"),
        ("Сценарий показа", "Code/docs/demo.md"),
        ("Демо без установки", DEMO + " — только просмотр, реальные люди показаны инициалами"),
    ]:
        row = table.add_row().cells
        row[0].text, row[1].text = label, value

    d.add_heading("Версии и зависимости", level=2)
    table = d.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    for label, value in VERSIONS:
        row = table.add_row().cells
        row[0].text, row[1].text = label, value

    d.add_heading("Запуск с Docker и MySQL (основной способ)", level=2)
    code_block(d, DOCKER)
    d.add_paragraph("Откройте http://localhost:8000/. Команда demo_users создаёт три учётные записи — "
                    "specialist, controller, head — и один раз печатает их пароли. load_tables загружает "
                    "семь таблиц исследования из Code/demo_data и запускает анализ. Остановка: "
                    "docker compose down.")

    d.add_heading("Запуск без Docker (Python 3.12, SQLite)", level=2)
    code_block(d, LOCAL)
    d.add_paragraph("Режим для проверки на ноутбуке: база — файл local.sqlite3, "
                    "отладочный режим включён. Для MySQL без Docker установите requirements-mysql.txt "
                    "и задайте DB_ENGINE=mysql и переменные MYSQL_* из .env.example.")

    d.add_heading("Проверка", level=2)
    code_block(d, CHECKS)
    d.add_paragraph("Первая команда запускает 65 тестов. Вторая возвращает код 200, когда база и миграции "
                    "в порядке. GitHub Actions на каждое изменение запроса на слияние запускает все 65 тестов "
                    "на MySQL 8.4; последний запуск успешен: " + CI_RUN + ". "
                    "Команда load_tables в конце печатает строку на английском:")
    code_block(d, ["Analysis: 70 records, 31 triggered, agreement with research marks 69/70"])
    d.add_paragraph("Она означает: проанализировано 70 записей, правила сработали на 31, с разметкой "
                    "исследования совпали 69 из 70. Повторный запуск анализа даёт те же статусы. 19.11.2026 "
                    "на чистом клоне пройдены оба способа запуска (Docker + MySQL и Python 3.12 + SQLite): "
                    "сверка 69 из 70, страница готовности отвечает 200.")

    d.add_heading("Основной сценарий за 5 минут", level=2)
    for step in SCENARIO:
        d.add_paragraph(step, style="List Number")

    d.add_heading("Данные", level=2)
    d.add_paragraph("Code/demo_data — семь таблиц исследования команды (И1, И2, И3, И4, И6, И8, И10), 70 записей. "
                    "Реальные ячейки есть в семи строках; подробно разобраны два реальных примера: генплан Ростова-на-Дону (И2) и торги в Угличе (И4). Остальные строки "
                    "синтетические. Таблицы составлены вручную по восьми источникам: НСПД, ЕГРН, кадастровая "
                    "оценка, ЕГРЮЛ, ГИС «Торги», акты органов власти субъектов РФ, сайты муниципалитетов, "
                    "протоколы комиссий. В правиле И6 сервис сам ищет ИНН участника решения среди ИНН "
                    "покупателя, его учредителей и руководителя (текущих и прежних) и сверяет результат "
                    "с отметкой исследователя (колонка «Совпадение ИНН в ЕГРЮЛ»). Связь через промежуточное "
                    "юрлицо, которого нет в таблицах, берётся из отметки исследователя. В правиле И10 сервис "
                    "считает эпизоды из перечня исследователя, объекты которых есть в таблицах других "
                    "индикаторов; участие лица в эпизоде — по записи исследователя. Автоматическая загрузка "
                    "выгрузок ЕГРЮЛ — задача пилота. "
                    "Таблица исследования — до 2 МиБ и 500 строк; вложение к объекту — до 5 МБ. Репозиторий открытый, поэтому ФИО "
                    "сокращены до инициалов, ИНН заменены условными кодами («ИНН П-001» и далее): одинаковый ИНН — один код "
                    "во всех таблицах, таблица соответствия нигде не хранится. Результат анализа от этого не меняется.")

    from docx.shared import Cm

    for table in d.tables:
        for row in table.rows:
            row.cells[0].width, row.cells[1].width = Cm(5), Cm(11.5)
            for paragraph in row.cells[0].paragraphs:
                for run in paragraph.runs:
                    run.bold = True
    for p in d.paragraphs:
        for run in p.runs:
            if run.font.name != "Courier New":
                run.font.color.rgb = RGBColor(0, 0, 0)
    d.save(OUT)
    print(f"готово: {OUT.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
