"""CRS detection and parsing for Swiss shapefiles."""

from __future__ import annotations

from pyproj import CRS

SWISS_CRS_HINT = (
    "Common Swiss CRS codes: EPSG:2056 (CH1903+ / LV95), EPSG:21781 (CH1903 / LV03)"
)


class CRSError(ValueError):
    """Raised when the source CRS cannot be determined or parsed."""


def parse_source_crs(source_crs: str | None) -> CRS | None:
    """Parse an optional user-supplied CRS string."""
    if source_crs is None:
        return None
    try:
        return CRS.from_user_input(source_crs)
    except Exception as exc:
        raise CRSError(f"Invalid --source-crs value {source_crs!r}: {exc}") from exc


def resolve_source_crs(shapefile_crs: str | None, override: str | None) -> CRS:
    """Resolve source CRS from shapefile metadata, with optional CLI override."""
    if override is not None:
        return parse_source_crs(override)

    if shapefile_crs:
        try:
            return CRS.from_user_input(shapefile_crs)
        except Exception as exc:
            raise CRSError(
                f"Could not parse CRS from shapefile .prj: {exc}. "
                f"Provide --source-crs explicitly. {SWISS_CRS_HINT}"
            ) from exc

    raise CRSError(
        "No CRS found in shapefile (.prj missing or empty). "
        f"Provide --source-crs. {SWISS_CRS_HINT}"
    )
