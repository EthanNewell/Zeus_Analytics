"""Условные коды ИНН в обезличенном наборе demo_data.

В demo_data ФИО сокращены до инициалов, а ИНН были заменены словами «ИНН скрыт». Тогда сервис
не может сам сравнить ИНН должностного лица и учредителей покупателя (правило И6). Скрипт
берёт исходные таблицы исследования (закрытые, в репозиторий не входят) и ставит на место
каждого «ИНН скрыт» условный код: «ИНН П-001», «ИНН П-002»… Один и тот же ИНН во всех таблицах
получает один код, разные — разные. Таблица соответствия нигде не сохраняется, поэтому по
коду ИНН не восстановить.

    python tools/pseudonymize_inn.py <папка исходных xlsx> demo_data

Правка идёт прямо в XML строк xlsx (как и обезличивание ФИО): openpyxl при пересохранении
теряет кешированные значения формул, и сверка с разметкой ломается.
"""

import re
import sys
import zipfile
from pathlib import Path

INN_RE = re.compile(r"ИНН\s*(\d{10}(?:\d{2})?)\b")
TEXT_RE = re.compile(r"(<t[^>]*>)(.*?)(</t>)", re.S)
HIDDEN = "ИНН скрыт"


def code_of(table):
    match = re.search(r"И(\d+)", table.name)
    return int(match.group(1)) if match else 0


def texts(archive):
    """(file, [text, …]) for every shared-strings and sheet XML part, in a fixed order."""
    parts = sorted(
        name
        for name in archive.namelist()
        if name.endswith(".xml") and ("sharedStrings" in name or "worksheets/sheet" in name)
    )
    return [
        (name, [m.group(2) for m in TEXT_RE.finditer(archive.read(name).decode())])
        for name in parts
    ]


def main(source_dir, demo_dir):
    sources = {code_of(path): path for path in Path(source_dir).glob("*.xlsx")}
    codes = {}
    for demo in sorted(Path(demo_dir).glob("*.xlsx"), key=code_of):
        source = sources.get(code_of(demo))
        if source is None:
            sys.exit(f"нет исходной таблицы для {demo.name}")
        with zipfile.ZipFile(source) as original, zipfile.ZipFile(demo) as masked:
            pairs = dict(texts(original))
            changed, replaced = {}, 0
            for name, masked_texts in texts(masked):
                if not any(HIDDEN in text for text in masked_texts):
                    continue
                original_texts = pairs[name]
                if len(original_texts) != len(masked_texts):
                    sys.exit(f"{demo.name}/{name}: строки не совпадают с исходной таблицей")
                new_texts = []
                for before, after in zip(original_texts, masked_texts, strict=True):
                    found = INN_RE.findall(before)
                    if after.count(HIDDEN) != len(found):
                        sys.exit(f"{demo.name}: число ИНН не совпадает в строке «{after[:60]}»")
                    for inn in found:
                        code = codes.setdefault(inn, f"П-{len(codes) + 1:03d}")
                        after = after.replace(HIDDEN, f"ИНН {code}", 1)
                        replaced += 1
                    new_texts.append(after)
                xml = masked.read(name).decode()
                pieces = iter(new_texts)
                changed[name] = TEXT_RE.sub(lambda m: m.group(1) + next(pieces) + m.group(3), xml)
            if not changed:
                continue
            tmp = demo.with_suffix(".tmp")
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as out:
                for item in masked.infolist():
                    data = (
                        changed[item.filename].encode()
                        if item.filename in changed
                        else masked.read(item)
                    )
                    out.writestr(item, data)
        tmp.replace(demo)
        print(f"{demo.name}: кодов поставлено {replaced}")
    print(f"разных ИНН: {len(codes)}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
