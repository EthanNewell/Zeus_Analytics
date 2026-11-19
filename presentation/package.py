"""Итоговый архив для сдачи в СДО: один zip со всеми материалами проекта.

    python3 presentation/package.py [папка_для_архива]

Перед запуском собраны: презентация (build.mjs --png, to_pptx.py), паспорт (passport.py),
инструкция (launch_doc.py), приложения (appendix.mjs), ролик (film/render.mjs).
Документы Word дублируются в PDF (LibreOffice), чтобы их одинаково читали люди и программы.
"""

import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
NAME = "Zeus_Analytics_Риски_в_кадастре"

# файл в архиве ← файл в presentation/
FILES = [
    ("1_Паспорт_проекта.docx", "Паспорт_проекта_Zeus_Analytics.docx"),
    ("2_Презентация.pdf", "kod-prozrachnosti.pdf"),
    ("2_Презентация.pptx", "kod-prozrachnosti.pptx"),
    ("3_Ролик_демонстрации.mp4", "video/kod-prozrachnosti-film.mp4"),
    ("4_Ссылка_и_инструкция_запуска.docx", "Ссылка_и_инструкция_запуска.docx"),
    ("5_Приложения.pdf", "Приложения_Zeus_Analytics.pdf"),
]
AS_PDF = {"1_Паспорт_проекта.docx", "4_Ссылка_и_инструкция_запуска.docx"}


def main():
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE
    missing = [src for _, src in FILES if not (HERE / src).exists()]
    if missing:
        sys.exit(f"нет файлов: {', '.join(missing)} — сначала соберите их (см. README)")
    archive = out_dir / f"{NAME}.zip"
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        entries = [(name, HERE / src) for name, src in FILES]
        for name, src in list(entries):
            if name in AS_PDF:
                copy = tmp / name
                copy.write_bytes(src.read_bytes())
                subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(tmp), str(copy)],
                               check=True, capture_output=True)
                entries.append((Path(name).with_suffix(".pdf").name, tmp / Path(name).with_suffix(".pdf").name))
        entries.sort()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for name, src in entries:
                z.write(src, f"{NAME}/{name}")
    size = archive.stat().st_size / 1024 / 1024
    print(f"готово: {archive} ({size:.1f} МБ, файлов: {len(entries)})")


if __name__ == "__main__":
    main()
