"""Small geometry helpers (no external GIS dependency)."""
from __future__ import annotations

import math


def _ring_contains(ring, x, y) -> bool:
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def geometry_contains(geom: dict, lon: float, lat: float) -> bool:
    t = geom.get("type")
    polys = [geom["coordinates"]] if t == "Polygon" else geom.get("coordinates", []) if t == "MultiPolygon" else []
    for poly in polys:
        if poly and _ring_contains(poly[0], lon, lat) and not any(_ring_contains(h, lon, lat) for h in poly[1:]):
            return True
    return False


def centroid(geom: dict) -> tuple[float, float] | None:
    t = geom.get("type")
    polys = [geom["coordinates"]] if t == "Polygon" else geom.get("coordinates", [])
    pts = [p for poly in polys for p in (poly[0] if poly else [])]
    if not pts:
        return None
    return sum(p[1] for p in pts) / len(pts), sum(p[0] for p in pts) / len(pts)


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def find_governorate(locations, lat, lon) -> str | None:
    if lat is None or lon is None:
        return None
    for loc in locations:
        if loc.geometry and geometry_contains(loc.geometry, lon, lat):
            return loc.name
    # coastal points slightly outside simplified polygons: nearest boundary vertex within 10 km
    best, bd = None, 10.0
    for loc in locations:
        if not loc.geometry:
            continue
        t = loc.geometry.get("type")
        polys = [loc.geometry["coordinates"]] if t == "Polygon" else loc.geometry.get("coordinates", [])
        for poly in polys:
            for x, y in (poly[0] if poly else []):
                d = haversine_km(lat, lon, y, x)
                if d < bd:
                    best, bd = loc.name, d
    return best
