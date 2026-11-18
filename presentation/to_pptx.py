"""PPTX-копия презентации: по картинке слайда на страницу (png/ из build.mjs --png)."""
from pathlib import Path
from pptx import Presentation
from pptx.util import Emu

here = Path(__file__).parent
prs = Presentation()
prs.slide_width, prs.slide_height = Emu(12192000), Emu(6858000)
for png in sorted((here / "png").glob("[0-9][0-9].png")):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_picture(str(png), 0, 0, width=prs.slide_width, height=prs.slide_height)
prs.save(here / "kod-prozrachnosti.pptx")
print("готово: presentation/kod-prozrachnosti.pptx")
