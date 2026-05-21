from pathlib import Path

import pytest

from shp_converter.crs import CRSError, resolve_source_crs
from shp_converter.geometry import GeometryError, convert_shapefile_to_area, list_layers
from shp_converter.geojson_writer import build_feature_collection

ROOT = Path(__file__).resolve().parent.parent
VD_SHP = ROOT / "test-data" / "vd" / "LAD_GEN_CANTON.shp"
GE_SHP = ROOT / "test-data" / "ge" / "CAD_LIMITE_CANTON.shp"


@pytest.fixture
def source_crs():
    return resolve_source_crs(None, "EPSG:2056")


def test_vd_produces_single_multipolygon(source_crs):
    geometry = convert_shapefile_to_area(str(VD_SHP), source_crs=source_crs)
    fc = build_feature_collection(geometry)

    assert len(fc["features"]) == 1
    assert fc["features"][0]["geometry"]["type"] in {"Polygon", "MultiPolygon"}

    coords = fc["features"][0]["geometry"]["coordinates"]
    # Spot-check a coordinate is lon/lat in Switzerland
    if fc["features"][0]["geometry"]["type"] == "MultiPolygon":
        lon, lat = coords[0][0][0]
    else:
        lon, lat = coords[0][0]

    assert 5.0 < lon < 11.0
    assert 45.0 < lat < 48.5


def test_ge_polygonizes_to_single_area(source_crs):
    geometry = convert_shapefile_to_area(str(GE_SHP), source_crs=source_crs)
    fc = build_feature_collection(geometry)

    assert len(fc["features"]) == 1
    assert fc["features"][0]["geometry"]["type"] in {"Polygon", "MultiPolygon"}


def test_missing_crs_requires_override():
    with pytest.raises(CRSError, match="No CRS found"):
        resolve_source_crs(None, None)


def test_invalid_geometry_type_rejected(source_crs, tmp_path):
    import geopandas as gpd
    import pyogrio
    from shapely.geometry import Point

    shp_path = tmp_path / "points.shp"
    gdf = gpd.GeoDataFrame({"id": [1]}, geometry=[Point(2600000, 1200000)], crs="EPSG:2056")
    pyogrio.write_dataframe(gdf, shp_path)

    with pytest.raises(GeometryError, match="Cannot convert Point"):
        convert_shapefile_to_area(str(shp_path), source_crs=source_crs)


def test_open_lines_rejected(source_crs, tmp_path):
    import geopandas as gpd
    import pyogrio
    from shapely.geometry import LineString

    shp_path = tmp_path / "open_lines.shp"
    gdf = gpd.GeoDataFrame(
        {"id": [1, 2]},
        geometry=[
            LineString([(0, 0), (1, 0)]),
            LineString([(1, 0), (1, 1)]),
        ],
        crs="EPSG:2056",
    )
    pyogrio.write_dataframe(gdf, shp_path)

    with pytest.raises(GeometryError, match="not closed|dangling"):
        convert_shapefile_to_area(str(shp_path), source_crs=source_crs)


def test_list_layers_finds_canton_vd():
    layers = list_layers(str(VD_SHP))
    assert len(layers) >= 1


def test_shp_check_reports_exact_match(tmp_path):
    from shp_converter.check import compare_shapefile_to_geojson
    from shp_converter.geojson_writer import write_geojson

    geometry = convert_shapefile_to_area(str(VD_SHP), source_crs=resolve_source_crs(None, "EPSG:2056"))
    geojson_path = tmp_path / "vd.json"
    write_geojson(geometry, geojson_path)

    result = compare_shapefile_to_geojson(
        VD_SHP,
        geojson_path,
        resolve_source_crs(None, "EPSG:2056"),
    )
    assert result.ok
