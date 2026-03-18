"""
Generate STAC Item JSONs for Nested-EAGLE forecast outputs.

Each pipeline run produces two outputs:
  1. Raw forecast — full model output (nested global + CONUS grid)
  2. Post-processed — split into separate global (GFS) and CONUS (HRRR 6km) files

STAC Items are written to a dedicated stac/ folder in blob storage,
separate from the data files. MPC Pro's GeoCatalog reads STAC Items
from this folder for ingestion and public distribution.

Blob layout:
  data/raw/{YYYY}/{MM}/{DD}/{HH}/forecast.nc
  data/postprocessed/{YYYY}/{MM}/{DD}/{HH}/global.nc
  data/postprocessed/{YYYY}/{MM}/{DD}/{HH}/conus.nc
  stac/collection.json
  stac/items/{YYYY}/{MM}/{DD}/{HH}/raw.json
  stac/items/{YYYY}/{MM}/{DD}/{HH}/postprocessed.json

Usage (standalone):
  python stac_item.py --config nested_eagle.yaml

Programmatic:
  from stac_item import write_stac_items
  paths = write_stac_items(ic_timestamp, version, output_storage_url)
"""

import argparse
import json
import os
import sys
from datetime import timezone

import pandas as pd

import utils

# --- Collection-level constants (defined once, same for every run) ---

COLLECTION_ID = "noaa-nested-eagle"

# Bounding boxes [west, south, east, north]
BBOX_GLOBAL = [-180.0, -90.0, 180.0, 90.0]
BBOX_CONUS = [-134.1, 21.1, -60.9, 52.6]

# Variables output by the model (14 total)
VARIABLES = [
    "geopotential",
    "temperature",
    "u_component_of_wind",
    "v_component_of_wind",
    "specific_humidity",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "2m_temperature",
    "mean_sea_level_pressure",
    "total_column_water_vapour",
    "surface_pressure",
    "total_precipitation_6hr",
    "100m_u_component_of_wind",
    "100m_v_component_of_wind",
]

PRESSURE_LEVELS = [50, 100, 150, 200, 250, 300, 400, 500, 600, 700, 850, 925, 1000]

FORECAST_HOURS = 240
FORECAST_STEP_HOURS = 6


def _base_properties(init_utc, forecast_end, version):
    """Shared STAC properties for both raw and post-processed items."""
    return {
        "datetime": None,
        "start_datetime": init_utc.isoformat(),
        "end_datetime": forecast_end.isoformat(),
        "forecast:reference_time": init_utc.isoformat(),
        "forecast:horizon": f"PT{FORECAST_HOURS}H",
        "forecast:step_hours": FORECAST_STEP_HOURS,
        "nested-eagle:version": version,
        "nested-eagle:variables": VARIABLES,
        "nested-eagle:pressure_levels": PRESSURE_LEVELS,
        "nested-eagle:global_resolution_deg": 0.25,
        "nested-eagle:conus_resolution_km": 6,
    }


def _make_geometry(bbox):
    """Build a GeoJSON Polygon from a bbox."""
    w, s, e, n = bbox
    return {
        "type": "Polygon",
        "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]],
    }


def _stac_links():
    """Links back to the collection (relative paths within stac/ folder)."""
    return [
        {"rel": "collection", "href": "../../collection.json", "type": "application/json"},
        {"rel": "parent", "href": "../../collection.json", "type": "application/json"},
    ]


def create_raw_stac_item(
    ic_timestamp: pd.Timestamp,
    version: str,
    output_storage_url: str,
) -> dict:
    """
    STAC Item for the raw (full model output) forecast.

    Asset: data/raw/{YYYY}/{MM}/{DD}/{HH}/forecast.nc
    """
    init_utc = ic_timestamp.astimezone(timezone.utc)
    folder = init_utc.strftime("%Y/%m/%d/%H")
    forecast_end = init_utc + pd.Timedelta(hours=FORECAST_HOURS)

    base_url = output_storage_url.rstrip("/")
    nc_href = f"{base_url}/data/raw/{folder}/forecast.nc"

    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": f"nested-eagle-raw-{init_utc.strftime('%Y%m%d-%H')}z",
        "geometry": _make_geometry(BBOX_GLOBAL),
        "bbox": BBOX_GLOBAL,
        "properties": {
            **_base_properties(init_utc, forecast_end, version),
            "nested-eagle:output_type": "raw",
        },
        "collection": COLLECTION_ID,
        "links": _stac_links(),
        "assets": {
            "forecast": {
                "href": nc_href,
                "type": "application/netcdf",
                "title": "Raw Forecast NetCDF (full nested grid)",
                "description": (
                    f"Nested-EAGLE {FORECAST_HOURS}h forecast initialized "
                    f"at {init_utc.strftime('%Y-%m-%d %H:%M')} UTC — "
                    f"full model output (global + CONUS nested grid)"
                ),
                "roles": ["data"],
            },
        },
    }


def create_postprocessed_stac_item(
    ic_timestamp: pd.Timestamp,
    version: str,
    output_storage_url: str,
) -> dict:
    """
    STAC Item for the post-processed forecast (global + CONUS split).

    Assets:
      data/postprocessed/{YYYY}/{MM}/{DD}/{HH}/global.nc  — GFS 0.25° global
      data/postprocessed/{YYYY}/{MM}/{DD}/{HH}/conus.nc   — HRRR 6km CONUS
    """
    init_utc = ic_timestamp.astimezone(timezone.utc)
    folder = init_utc.strftime("%Y/%m/%d/%H")
    forecast_end = init_utc + pd.Timedelta(hours=FORECAST_HOURS)

    base_url = output_storage_url.rstrip("/")
    global_href = f"{base_url}/data/postprocessed/{folder}/global.nc"
    conus_href = f"{base_url}/data/postprocessed/{folder}/conus.nc"

    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": f"nested-eagle-postprocessed-{init_utc.strftime('%Y%m%d-%H')}z",
        "geometry": _make_geometry(BBOX_GLOBAL),
        "bbox": BBOX_GLOBAL,
        "properties": {
            **_base_properties(init_utc, forecast_end, version),
            "nested-eagle:output_type": "postprocessed",
        },
        "collection": COLLECTION_ID,
        "links": _stac_links(),
        "assets": {
            "global": {
                "href": global_href,
                "type": "application/netcdf",
                "title": "Global Forecast (GFS grid, 0.25°)",
                "description": (
                    f"Global forecast on GFS 0.25° grid, "
                    f"{FORECAST_HOURS}h from {init_utc.strftime('%Y-%m-%d %H:%M')} UTC"
                ),
                "roles": ["data"],
            },
            "conus": {
                "href": conus_href,
                "type": "application/netcdf",
                "title": "CONUS Forecast (HRRR grid, 6km)",
                "description": (
                    f"CONUS regional forecast on HRRR 6km grid, "
                    f"{FORECAST_HOURS}h from {init_utc.strftime('%Y-%m-%d %H:%M')} UTC"
                ),
                "roles": ["data"],
                "proj:bbox": BBOX_CONUS,
            },
        },
    }


def write_stac_items(
    ic_timestamp: pd.Timestamp,
    version: str,
    output_storage_url: str,
) -> list[str]:
    """
    Create STAC Items for both raw and post-processed outputs and write
    them to a local stac/items/ folder (mirroring the blob layout).

    Returns list of paths to the written JSON files.
    """
    folder = ic_timestamp.strftime("%Y/%m/%d/%H")
    stac_dir = f"{version}/stac/items/{folder}"
    os.makedirs(stac_dir, exist_ok=True)

    paths = []

    # Raw forecast STAC Item
    raw_item = create_raw_stac_item(ic_timestamp, version, output_storage_url)
    raw_path = os.path.join(stac_dir, "raw.json")
    with open(raw_path, "w") as f:
        json.dump(raw_item, f, indent=2)
    print(f"STAC Item written: {raw_path}")
    paths.append(raw_path)

    # Post-processed forecast STAC Item
    pp_item = create_postprocessed_stac_item(ic_timestamp, version, output_storage_url)
    pp_path = os.path.join(stac_dir, "postprocessed.json")
    with open(pp_path, "w") as f:
        json.dump(pp_item, f, indent=2)
    print(f"STAC Item written: {pp_path}")
    paths.append(pp_path)

    return paths


def run(version: str, output_storage_url: str):
    """Generate STAC Items for the current NRT cycle."""
    ic_timestamp = utils.get_nrt_timestamp()
    write_stac_items(ic_timestamp, version, output_storage_url)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate STAC Items for a Nested-EAGLE forecast"
    )
    parser.add_argument("--config", required=True, help="Path to config YAML")
    args = parser.parse_args()

    config = utils.load_config(args.config)
    version = config["version"]
    output_storage_url = config.get(
        "output_storage_url",
        "https://STORAGE_ACCOUNT.blob.core.windows.net/nested-eagle-forecasts",
    )

    run(version=version, output_storage_url=output_storage_url)
