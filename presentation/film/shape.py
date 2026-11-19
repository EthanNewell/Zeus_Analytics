"""Контур участка 61:02:0120105:331 и его наименьший описанный прямоугольник — для сцены «Геометрия».

Тот же расчёт, что в Code/cases/geometry.py (проекция и вращающиеся калиперы), плюс углы
прямоугольника, которых модуль не возвращает. Координаты — из таблицы И8 (demo_data).
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "Code"))
from cases.geometry import convex_hull, polygon_area, project  # noqa: E402

POINTS = [[47.2618, 39.853], [47.2618, 39.853529], [47.262069, 39.853529], [47.262069, 39.853291],
          [47.262213, 39.853291], [47.262267, 39.85341], [47.262339, 39.853344], [47.262339, 39.853251],
          [47.262222, 39.853225], [47.262069, 39.853212], [47.262069, 39.853]]

xy = project(POINTS)
cx, cy = sum(p[0] for p in xy) / len(xy), sum(p[1] for p in xy) / len(xy)
xy = [(x - cx, y - cy) for x, y in xy]
hull = convex_hull(xy)
best = None
for i in range(len(hull)):
    a, b = hull[i], hull[(i + 1) % len(hull)]
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    c, s = math.cos(-ang), math.sin(-ang)
    rot = [(x * c - y * s, x * s + y * c) for x, y in hull]
    xs, ys = [p[0] for p in rot], [p[1] for p in rot]
    area = (max(xs) - min(xs)) * (max(ys) - min(ys))
    if best is None or area < best[0]:
        corners = [(min(xs), min(ys)), (max(xs), min(ys)), (max(xs), max(ys)), (min(xs), max(ys))]
        cb, sb = math.cos(ang), math.sin(ang)
        best = (area, [(x * cb - y * sb, x * sb + y * cb) for x, y in corners])
area = polygon_area(xy)
out = {"polygon": xy, "rectangle": best[1], "area": area, "rect_area": best[0], "fill": area / best[0]}
(Path(__file__).parent / "shape.json").write_text(json.dumps(out))
print(f"площадь {area:.0f} м², прямоугольник {best[0]:.0f} м², заполнение {area / best[0]:.3f}")
