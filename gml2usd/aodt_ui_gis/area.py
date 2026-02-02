"""
Minimal replacement for the external `area` package.

The official AODT GIS code imports:
    from area import area

In some environments, the PyPI `area` dependency may not be available.
This module provides a compatible `area(geojson)` function that returns
polygon area in **square meters** for GeoJSON Polygon objects.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence, Tuple


def _iter_rings(geojson: dict) -> Iterable[Sequence[Sequence[float]]]:
    if not isinstance(geojson, dict):
        raise TypeError("geojson must be a dict")
    if geojson.get("type") != "Polygon":
        raise ValueError(f"Unsupported geojson type: {geojson.get('type')!r} (only 'Polygon' supported)")
    coords = geojson.get("coordinates")
    if not isinstance(coords, list) or not coords:
        raise ValueError("Invalid Polygon coordinates")
    # coords: [ring0, ring1, ...], ring: [[lon,lat], ...]
    for ring in coords:
        if not isinstance(ring, list) or len(ring) < 4:
            continue
        yield ring


def area(geojson: dict) -> float:
    """
    Compute polygon area (m^2) for a GeoJSON Polygon.

    Uses pyproj.Geod if available (geodesic, WGS84). Falls back to a very rough
    planar shoelace on lon/lat degrees (NOT meters) if pyproj is unavailable.
    """

    rings = list(_iter_rings(geojson))
    if not rings:
        return 0.0

    try:
        from pyproj import Geod  # type: ignore

        geod = Geod(ellps="WGS84")

        total = 0.0
        for ring in rings:
            lons = [float(p[0]) for p in ring]
            lats = [float(p[1]) for p in ring]
            a, _ = geod.polygon_area_perimeter(lons, lats)
            total += a
        return abs(float(total))
    except Exception:
        # Fallback: planar shoelace on (lon, lat) degrees -> NOT real meters.
        # Keep behavior stable (non-crashing) for code paths that don't care
        # about exact area, e.g. debug checks.
        def shoelace(poly: Sequence[Sequence[float]]) -> float:
            s = 0.0
            for i in range(len(poly) - 1):
                x1, y1 = float(poly[i][0]), float(poly[i][1])
                x2, y2 = float(poly[i + 1][0]), float(poly[i + 1][1])
                s += x1 * y2 - x2 * y1
            return 0.5 * abs(s)

        return float(sum(shoelace(r) for r in rings))




