# Shapefile → PostGIS-ready GeoJSON

Convert to a single **Polygon** or **MultiPolygon** GeoJSON feature, suitable for PostGIS import.

Handles two common cases:

- **Polygon shapefiles** — merged and reprojected to WGS84
- **Polyline boundary shapefiles** — polygonized, merged, reprojected (e.g. Geneva canton limits stored as 749 line segments)

## Requirements

- [uv](https://docs.astral.sh/uv/) (recommended)
- No system GDAL required for local dev (`pyogrio` wheels bundle it)

## Setup

```bash
uv sync --group dev
```

## Usage

```bash
# Convert to file
uv run shp2geojson test-data/ge/CAD_LIMITE_CANTON.shp -o canton-ge-out.json

# Print to stdout
uv run shp2geojson test-data/vd/LAD_GEN_CANTON.shp

# Override CRS when .prj is missing
uv run shp2geojson input.shp -o output.json --source-crs EPSG:2056

# Optional metadata
uv run shp2geojson input.shp -o output.json --name "Geneva" --properties-json props.json
```

### CLI options

| Flag | Description |
|------|-------------|
| `INPUT.shp` | Input shapefile path |
| `-o`, `--output` | Output GeoJSON path (default: stdout) |
| `--source-crs` | Source CRS override (`EPSG:2056`, `EPSG:21781`, or WKT). Required if `.prj` is missing. |
| `--layer` | Layer name (default: first layer) |
| `--name` | Sets `properties.name` on the output feature |
| `--properties-json` | JSON object merged into output feature properties |

### Common Swiss CRS codes

- **EPSG:2056** — CH1903+ / LV95 (modern Swiss projected CRS)
- **EPSG:21781** — CH1903 / LV03 (legacy)

## Docker

```bash
docker build -t shp-converter .
docker run --rm -v "$PWD:/data" shp-converter \
  /data/test-data/ge/CAD_LIMITE_CANTON.shp -o /data/canton-ge-out.json
```

## Output format

Always a RFC 7946 `FeatureCollection` with **one feature** and WGS84 coordinates:

```json
{
  "type": "FeatureCollection",
  "features": [{
    "type": "Feature",
    "properties": {},
    "geometry": { "type": "MultiPolygon", "coordinates": [...] }
  }]
}
```

## PostGIS import

After conversion, load the geometry into a `geometry` column:

```sql
SELECT ST_SetSRID(
  ST_GeomFromGeoJSON(
    (SELECT features->0->'geometry' FROM (
      SELECT pg_read_file('/path/to/output.json')::jsonb->'features' AS features
    ) t)
  ),
  4326
);
```

Or use `ogr2ogr -f PostgreSQL` on the output GeoJSON.

## Tests

```bash
uv run pytest
```

Fixtures in `test-data/vd/` (polygon) and `test-data/ge/` (lines → polygonize).

## Verify conversion accuracy

Compare a GeoJSON output against its source shapefile in native CRS (e.g. EPSG:2056).
Use this to confirm the converter did not introduce a shift — discrepancies vs OSM on
geojson.io are usually from different data sources, not from reprojection.

```bash
uv run shp2geojson test-data/vd/LAD_GEN_CANTON.shp -o test.geojson
uv run shp-check test-data/vd/LAD_GEN_CANTON.shp test.geojson
```

Reports symmetric difference area, Hausdorff distance, and max vertex delta in meters.
Exits with code 1 if geometries differ in source CRS.

## Errors

The CLI exits with an error when:

- CRS cannot be determined and `--source-crs` was not provided
- Geometries are Points or other non-area types
- Line boundaries are not closed (dangling segments)
- Polygonization produces no area
