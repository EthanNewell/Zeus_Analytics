"""Plot geometry on a local equirectangular projection (enough for plots of a few km)."""

import math

EARTH_RADIUS_M = 6371008.8


def project(points):
    lat0 = sum(lat for lat, _ in points) / len(points)
    scale = math.cos(math.radians(lat0))
    return [
        (math.radians(lon) * EARTH_RADIUS_M * scale, math.radians(lat) * EARTH_RADIUS_M)
        for lat, lon in points
    ]


def polygon_area(xy):
    return abs(sum(xy[i][0] * xy[i - 1][1] - xy[i - 1][0] * xy[i][1] for i in range(len(xy)))) / 2


def convex_hull(xy):
    points = sorted(set(xy))
    if len(points) < 3:
        return points

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for point in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    for point in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def min_rectangle_area(xy):
    """Smallest rotated bounding rectangle (rotating calipers over hull edges)."""
    hull = convex_hull(xy)
    best = None
    for index in range(len(hull)):
        a, b = hull[index], hull[(index + 1) % len(hull)]
        angle = math.atan2(b[1] - a[1], b[0] - a[0])
        cos, sin = math.cos(-angle), math.sin(-angle)
        rotated = [(x * cos - y * sin, x * sin + y * cos) for x, y in hull]
        xs = [point[0] for point in rotated]
        ys = [point[1] for point in rotated]
        area = (max(xs) - min(xs)) * (max(ys) - min(ys))
        best = area if best is None or area < best else best
    return best or 0.0


def shape_metrics(points):
    """Area, rectangle area and fill ratio of a lat/lon contour."""
    xy = project(points)
    area = polygon_area(xy)
    rectangle = min_rectangle_area(xy)
    return {
        "area": area,
        "rectangle": rectangle,
        "fill": area / rectangle if rectangle else None,
    }


def centroid(points):
    return [
        sum(lat for lat, _ in points) / len(points),
        sum(lon for _, lon in points) / len(points),
    ]
