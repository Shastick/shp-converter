"""Compare a GeoJSON output against its source shapefile in native CRS."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import click
from pyproj import CRS, Transformer
from shapely import get_coordinates
from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

from shp_converter.crs import CRSError, resolve_source_crs
from shp_converter.geometry import (
    GeometryError,
    convert_shapefile_to_area_native,
    list_layers,
    read_shapefile_crs,
)

WGS84 = CRS.from_epsg(4326)
DEFAULT_TOLERANCE_M = 0.01


@dataclass(frozen=True)
class ComparisonResult:
    source_crs: str
    reference_area_m2: float
    symmetric_difference_area_m2: float
    hausdorff_distance_m: float
    max_vertex_delta_m: float
    max_reverse_vertex_delta_m: float
    tolerance_m: float

    @property
    def ok(self) -> bool:
        max_delta = max(
            self.hausdorff_distance_m,
            self.max_vertex_delta_m,
            self.max_reverse_vertex_delta_m,
        )
        return max_delta <= self.tolerance_m


def _boundary(geometry: BaseGeometry) -> BaseGeometry:
    if geometry.geom_type in {"Polygon", "LineString", "LinearRing"}:
        return geometry.boundary
    if geometry.geom_type == "MultiPolygon":
        from shapely.ops import unary_union

        return unary_union([part.boundary for part in geometry.geoms])
    return geometry


def _max_vertex_delta(reference: BaseGeometry, comparison: BaseGeometry) -> float:
    boundary = _boundary(comparison)
    coords = get_coordinates(reference)
    if len(coords) == 0:
        return 0.0
    return max(Point(x, y).distance(boundary) for x, y in coords)


def _load_geojson_geometry(geojson_path: Path) -> BaseGeometry:
    with geojson_path.open(encoding="utf-8") as handle:
        payload = json.load(handle)

    if payload.get("type") == "FeatureCollection":
        features = payload.get("features") or []
        if len(features) != 1:
            raise GeometryError(
                f"Expected GeoJSON FeatureCollection with 1 feature, got {len(features)}."
            )
        geometry_payload = features[0].get("geometry")
    elif payload.get("type") == "Feature":
        geometry_payload = payload.get("geometry")
    elif payload.get("type") in {"Polygon", "MultiPolygon"}:
        geometry_payload = payload
    else:
        raise GeometryError("GeoJSON must be a FeatureCollection, Feature, or Polygon geometry.")

    if geometry_payload is None:
        raise GeometryError("GeoJSON feature has no geometry.")

    geometry = shape(geometry_payload)
    if geometry.is_empty:
        raise GeometryError("GeoJSON geometry is empty.")
    if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        raise GeometryError(
            f"GeoJSON geometry must be Polygon or MultiPolygon, got {geometry.geom_type}."
        )
    return geometry


def _reproject_to_source(geometry: BaseGeometry, source_crs: CRS) -> BaseGeometry:
    transformer = Transformer.from_crs(WGS84, source_crs, always_xy=True)
    return transform(transformer.transform, geometry)


def compare_shapefile_to_geojson(
    shapefile_path: str | Path,
    geojson_path: str | Path,
    source_crs: CRS,
    layer: str | None = None,
    tolerance_m: float = DEFAULT_TOLERANCE_M,
) -> ComparisonResult:
    reference = convert_shapefile_to_area_native(str(shapefile_path), source_crs, layer)
    geojson_geometry = _load_geojson_geometry(Path(geojson_path))
    comparison = _reproject_to_source(geojson_geometry, source_crs)

    symmetric_difference = reference.symmetric_difference(comparison)

    return ComparisonResult(
        source_crs=source_crs.to_string(),
        reference_area_m2=reference.area,
        symmetric_difference_area_m2=symmetric_difference.area,
        hausdorff_distance_m=reference.hausdorff_distance(comparison),
        max_vertex_delta_m=_max_vertex_delta(reference, comparison),
        max_reverse_vertex_delta_m=_max_vertex_delta(comparison, reference),
        tolerance_m=tolerance_m,
    )


def format_comparison(result: ComparisonResult) -> str:
    lines = [
        f"CRS: {result.source_crs}",
        f"Reference area: {result.reference_area_m2:,.3f} m²",
        f"Symmetric difference area: {result.symmetric_difference_area_m2:.6f} m²",
        f"Hausdorff distance: {result.hausdorff_distance_m:.6f} m",
        f"Max vertex delta (shapefile → GeoJSON): {result.max_vertex_delta_m:.6f} m",
        f"Max vertex delta (GeoJSON → shapefile): {result.max_reverse_vertex_delta_m:.6f} m",
        f"Tolerance: {result.tolerance_m:.3f} m",
    ]
    if result.ok:
        lines.append("Result: match within tolerance (conversion did not introduce meaningful shift)")
    else:
        lines.append("Result: geometries differ beyond tolerance in source CRS")
    return "\n".join(lines)


@click.command()
@click.argument("input_shp", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("geojson", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--source-crs",
    help="Override source CRS (e.g. EPSG:2056). Required when .prj is missing.",
)
@click.option("--layer", help="Shapefile layer name (default: first layer).")
@click.option(
    "--tolerance-m",
    default=DEFAULT_TOLERANCE_M,
    show_default=True,
    help="Pass if all distances are within this threshold (meters).",
)
def main(
    input_shp: Path,
    geojson: Path,
    source_crs: str | None,
    layer: str | None,
    tolerance_m: float,
) -> None:
    """Check how closely a GeoJSON output matches its source shapefile."""
    try:
        if layer is None:
            layers = list_layers(str(input_shp))
            if len(layers) == 0:
                raise click.ClickException("No layers found in shapefile.")
            layer = layers[0]

        resolved_crs = resolve_source_crs(read_shapefile_crs(str(input_shp), layer=layer), source_crs)
        result = compare_shapefile_to_geojson(
            input_shp,
            geojson,
            resolved_crs,
            layer=layer,
            tolerance_m=tolerance_m,
        )
        click.echo(format_comparison(result))
        if not result.ok:
            raise SystemExit(1)
    except (CRSError, GeometryError) as exc:
        raise click.ClickException(str(exc)) from exc


if __name__ == "__main__":
    main()
