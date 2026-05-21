"""CLI entrypoint for shp2geojson."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from shp_converter.crs import CRSError, resolve_source_crs
from shp_converter.geometry import GeometryError, convert_shapefile_to_area, list_layers, read_shapefile_crs
from shp_converter.geojson_writer import write_geojson


@click.command()
@click.argument("input_shp", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "-o",
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Output GeoJSON path (default: stdout).",
)
@click.option(
    "--source-crs",
    help="Override source CRS (e.g. EPSG:2056, EPSG:21781, or WKT). "
    "Required when .prj is missing.",
)
@click.option(
    "--layer",
    help="Shapefile layer name (default: first layer).",
)
@click.option(
    "--name",
    help="Optional value for output feature properties.name.",
)
@click.option(
    "--properties-json",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Optional JSON file with static properties merged into the output feature.",
)
def main(
    input_shp: Path,
    output_path: Path | None,
    source_crs: str | None,
    layer: str | None,
    name: str | None,
    properties_json: Path | None,
) -> None:
    """Convert a Swiss shapefile to PostGIS-ready GeoJSON (Polygon/MultiPolygon)."""
    try:
        if layer is None:
            layers = list_layers(str(input_shp))
            if len(layers) == 0:
                raise click.ClickException("No layers found in shapefile.")
            layer = layers[0]

        shapefile_crs = read_shapefile_crs(str(input_shp), layer=layer)
        resolved_crs = resolve_source_crs(shapefile_crs, source_crs)

        geometry = convert_shapefile_to_area(
            str(input_shp),
            source_crs=resolved_crs,
            layer=layer,
        )

        properties: dict = {}
        if properties_json is not None:
            with properties_json.open(encoding="utf-8") as handle:
                loaded = json.load(handle)
            if not isinstance(loaded, dict):
                raise click.ClickException("--properties-json must contain a JSON object.")
            properties.update(loaded)
        if name is not None:
            properties["name"] = name

        if output_path is None:
            from shp_converter.geojson_writer import build_feature_collection

            click.echo(json.dumps(build_feature_collection(geometry, properties), ensure_ascii=False))
        else:
            write_geojson(geometry, output_path, properties)
    except (CRSError, GeometryError) as exc:
        raise click.ClickException(str(exc)) from exc


if __name__ == "__main__":
    main()
