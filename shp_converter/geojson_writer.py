"""Write PostGIS-ready GeoJSON FeatureCollections."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shapely.geometry import MultiPolygon, Polygon, mapping


def build_feature_collection(
    geometry: Polygon | MultiPolygon,
    properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": properties or {},
                "geometry": mapping(geometry),
            }
        ],
    }


def write_geojson(
    geometry: Polygon | MultiPolygon,
    output_path: Path,
    properties: dict[str, Any] | None = None,
) -> None:
    feature_collection = build_feature_collection(geometry, properties)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(feature_collection, handle, ensure_ascii=False)
