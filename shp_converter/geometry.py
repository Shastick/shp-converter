"""Read shapefiles and normalize geometry to Polygon/MultiPolygon."""

from __future__ import annotations

from collections.abc import Iterable

import pyogrio
from pyogrio.raw import read as read_raw
from pyproj import CRS, Transformer
from shapely import from_wkb, make_valid
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import polygonize_full, transform, unary_union

ALLOWED_AREA_TYPES = frozenset({"Polygon", "MultiPolygon"})
ALLOWED_LINE_TYPES = frozenset({"LineString", "MultiLineString"})
WGS84 = CRS.from_epsg(4326)


class GeometryError(ValueError):
    """Raised when geometry cannot be converted to a polygon area."""


def _iter_lines(geometry: BaseGeometry) -> Iterable[LineString]:
    if isinstance(geometry, LineString):
        yield geometry
    elif isinstance(geometry, MultiLineString):
        yield from geometry.geoms
    else:
        raise GeometryError(
            f"Expected LineString or MultiLineString, got {geometry.geom_type}"
        )


def _collect_geometries(shapefile_path: str, layer: str | None) -> list[BaseGeometry]:
    kwargs: dict = {"read_geometry": True}
    if layer is not None:
        kwargs["layer"] = layer

    _meta, _fids, wkb_geometries, _fields = read_raw(shapefile_path, **kwargs)
    if wkb_geometries is None or len(wkb_geometries) == 0:
        raise GeometryError("Shapefile contains no features")

    geometries = [from_wkb(wkb) for wkb in wkb_geometries if wkb is not None]
    geometries = [geom for geom in geometries if not geom.is_empty]
    if not geometries:
        raise GeometryError("Shapefile contains no non-empty geometries")

    return geometries


def _classify_geometries(geometries: list[BaseGeometry]) -> tuple[list[BaseGeometry], list[BaseGeometry]]:
    polygons: list[BaseGeometry] = []
    lines: list[BaseGeometry] = []

    for geometry in geometries:
        geom_type = geometry.geom_type
        if geom_type in ALLOWED_AREA_TYPES:
            polygons.append(geometry)
        elif geom_type in ALLOWED_LINE_TYPES:
            lines.append(geometry)
        else:
            raise GeometryError(
                f"Cannot convert {geom_type} to polygon area. "
                "Only Polygon, MultiPolygon, LineString, and MultiLineString are supported."
            )

    if polygons and lines:
        raise GeometryError(
            "Shapefile mixes polygon and line geometries; cannot produce a single area."
        )

    return polygons, lines


def _polygonize_lines(lines: list[BaseGeometry]) -> BaseGeometry:
    merged_lines = unary_union(lines)
    polygons, cuts, dangles, invalid = polygonize_full(merged_lines)

    if not dangles.is_empty:
        raise GeometryError(
            f"Boundary lines are not closed ({len(dangles.geoms)} dangling segment(s)). "
            "Cannot polygonize to an area."
        )
    if not invalid.is_empty:
        raise GeometryError(
            f"Boundary lines contain invalid ring segments "
            f"({len(invalid.geoms)} segment(s)). Cannot polygonize to an area."
        )

    polygon_list = list(polygons.geoms)
    if not polygon_list:
        raise GeometryError("Line geometries did not form any closed polygon area.")

    return unary_union(polygon_list)


def _merge_polygons(polygons: list[BaseGeometry]) -> BaseGeometry:
    return unary_union(polygons)


def _normalize_area_geometry(geometry: BaseGeometry) -> Polygon | MultiPolygon:
    if isinstance(geometry, Polygon):
        return geometry
    if isinstance(geometry, MultiPolygon):
        return geometry

    if geometry.geom_type == "GeometryCollection":
        parts = [
            part
            for part in geometry.geoms
            if isinstance(part, (Polygon, MultiPolygon))
        ]
        if not parts:
            raise GeometryError("GeometryCollection contains no polygon parts.")
        return _normalize_area_geometry(unary_union(parts))

    raise GeometryError(
        f"Expected Polygon or MultiPolygon after merge, got {geometry.geom_type}"
    )


def _ensure_valid(geometry: Polygon | MultiPolygon) -> Polygon | MultiPolygon:
    if geometry.is_valid:
        return geometry

    repaired = make_valid(geometry)
    if isinstance(repaired, (Polygon, MultiPolygon)) and repaired.is_valid:
        return repaired

    raise GeometryError("Resulting polygon geometry is invalid and could not be repaired.")


def _reproject(geometry: BaseGeometry, source_crs: CRS) -> Polygon | MultiPolygon:
    transformer = Transformer.from_crs(source_crs, WGS84, always_xy=True)
    reprojected = transform(transformer.transform, geometry)
    return _normalize_area_geometry(reprojected)


def convert_shapefile_to_area_native(
    shapefile_path: str,
    source_crs: CRS,
    layer: str | None = None,
) -> Polygon | MultiPolygon:
    """Read a shapefile and return a single Polygon or MultiPolygon in source CRS."""
    del source_crs  # Geometries are already stored in the shapefile's native CRS.
    geometries = _collect_geometries(shapefile_path, layer)
    polygons, lines = _classify_geometries(geometries)

    if polygons:
        merged = _merge_polygons(polygons)
    else:
        merged = _polygonize_lines(lines)

    area = _normalize_area_geometry(merged)
    return _ensure_valid(area)


def convert_shapefile_to_area(
    shapefile_path: str,
    source_crs: CRS,
    layer: str | None = None,
) -> Polygon | MultiPolygon:
    """Read a shapefile and return a single Polygon or MultiPolygon in WGS84."""
    area = convert_shapefile_to_area_native(shapefile_path, source_crs, layer)
    return _reproject(area, source_crs)


def read_shapefile_crs(shapefile_path: str, layer: str | None = None) -> str | None:
    """Return CRS WKT/PROJ string from shapefile metadata, if present."""
    kwargs: dict = {}
    if layer is not None:
        kwargs["layer"] = layer
    info = pyogrio.read_info(shapefile_path, **kwargs)
    crs = info.get("crs")
    return str(crs) if crs else None


def list_layers(shapefile_path: str) -> list[str]:
    layers = pyogrio.list_layers(shapefile_path)
    if len(layers) == 0:
        return []
    return [str(row[0]) for row in layers]
