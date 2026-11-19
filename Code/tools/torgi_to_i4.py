"""Таблица И4 из выгрузки torgi_fetch.py: реальные земельные торги в формате таблицы исследования.

    python tools/torgi_to_i4.py real_data/torgi_61_2026-11-19.json real_data/Реальные_торги_И4.xlsx

Все ячейки — открытые данные ГИС «Торги», поэтому залиты жёлтым, как реальные ячейки в
таблицах исследования: сервис покажет их происхождение «реальное». Колонка «Соответствие
индикатору» пустая: разметки исследователя у этих строк нет, в сверку они не входят.
"""

import json
import sys
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

sys.path.insert(0, __file__.rsplit("/tools/", 1)[0])
import django  # noqa: E402

django.setup()

from cases.indicators import INDICATORS  # noqa: E402

YELLOW = PatternFill("solid", fgColor="FFFF00")
CONTRACT = {
    "rent": "Договор аренды земельного участка",
    "sale": "Договор купли-продажи земельного участка",
}


def day(value):
    return (
        datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%d.%m.%Y")
        if value
        else "нет даты"
    )


def money(value):
    return float(value) if value is not None else None


def rows(lots):
    seen = set()
    for lot in lots:
        key = lot["cadastral"] or lot["id"]
        if key in seen:
            continue
        seen.add(key)
        single = lot["kind"] == "single"
        area = f", {float(lot['area']):,.0f} кв. м".replace(",", " ") if lot.get("area") else ""
        protocol = ", ".join(n for n in lot["protocol_numbers"] if n)
        yield {
            "object": f"Земельный участок ({lot['category'] or 'категория не указана'}), {lot['address']}, КН {lot['cadastral']}{area}",
            "seller": f"Собственность: {lot['ownership'] or 'не указана'} (организатор — по извещению № {lot['notice']})",
            "method": f"{lot['form']} по ст. 39.11–39.12 ЗК РФ; извещение № {lot['notice']}; {lot['url']}",
            "contract": f"{lot.get('contract') or CONTRACT.get(lot.get('transaction'), 'Договор')}; протокол № {protocol} от {day(lot['protocol_date'])}",
            "participants": 1 if single else None,
            "start_price": money(lot["price_min"]),
            "final_price": money(lot["price_fin"]),
            "counterparty": (
                "Единственный участник (подана одна заявка); наименование в открытых данных не публикуется"
                if single
                else "Победитель аукциона; в протоколе указаны победитель и участник со вторым предложением"
            ),
            "bypass": "Нет",
            "mark": None,
        }


def main(source, target):
    lots = json.load(open(source, encoding="utf-8"))
    columns = INDICATORS["I4"].columns
    wb = Workbook()
    ws = wb.active
    ws.title = "И4 — реальные торги"
    ws.append([column.header for column in columns])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    count = 0
    for count, row in enumerate(rows(lots), start=1):
        values = [count if column.key == "number" else row.get(column.key) for column in columns]
        ws.append(values)
        for cell, column in zip(ws[ws.max_row], columns, strict=True):
            if column.key != "mark":
                cell.fill = YELLOW
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.append([])
    ws.append(
        [
            "Источник: ГИС «Торги» (torgi.gov.ru), открытые данные; выгрузка 19.11.2026 скриптом tools/torgi_fetch.py. "
            "Жёлтая заливка — реальные данные. Имена участников торгов в открытых данных не публикуются."
        ]
    )
    ws.append(
        [
            "Строки с одним участником — аукционы, признанные несостоявшимися: подана только одна заявка "
            "(п. 14 ст. 39.12 ЗК РФ), договор заключается с единственным участником по начальной цене. "
            "Остальные строки — состоявшиеся аукционы с ростом цены."
        ]
    )
    for letter, width in zip(
        "ABCDEFGHIJK", (5, 60, 40, 60, 45, 12, 16, 16, 45, 20, 18), strict=False
    ):
        ws.column_dimensions[letter].width = width
    wb.save(target)
    print(f"готово: {target}, строк {count}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
