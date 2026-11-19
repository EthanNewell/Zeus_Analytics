"""Обрезать поля снимков сервиса по содержимому, чтобы край кадра совпал с краем текста слайда."""
import sys
from pathlib import Path
from PIL import Image, ImageChops

for name in sys.argv[1:]:
    path = Path(__file__).parent / "img" / name
    im = Image.open(path).convert("RGB")
    bg = Image.new("RGB", im.size, im.getpixel((2, 2)))
    diff = ImageChops.difference(im, bg).convert("L").point(lambda v: 255 if v > 24 else 0)
    box = diff.getbbox()
    im.crop(box).save(path)
    print(name, im.size, "→", (box[2] - box[0], box[3] - box[1]))
