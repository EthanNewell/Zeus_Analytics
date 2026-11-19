"""PPTX-копия презентации: картинка слайда на страницу (png/ из build.mjs --png).

Текст каждого слайда (png/text.json) кладётся в заметки докладчика и в описание картинки:
так его видят поиск, программы чтения с экрана и автоматическая проверка материалов.
"""
import json
from pathlib import Path

from pptx import Presentation
from pptx.util import Emu

here = Path(__file__).parent
texts = json.loads((here / "png" / "text.json").read_text())
prs = Presentation()
prs.slide_width, prs.slide_height = Emu(12192000), Emu(6858000)
prs.core_properties.title = "Код прозрачности — Zeus Analytics"
prs.core_properties.subject = "Рабочее место специалиста по профилактике коррупции в земельных отношениях"
for png, text in zip(sorted((here / "png").glob("[0-9][0-9].png")), texts):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    pic = slide.shapes.add_picture(str(png), 0, 0, width=prs.slide_width, height=prs.slide_height)
    pic._element.nvPicPr.cNvPr.set("descr", text)
    slide.notes_slide.notes_text_frame.text = text
prs.save(here / "kod-prozrachnosti.pptx")
print("готово: presentation/kod-prozrachnosti.pptx")
