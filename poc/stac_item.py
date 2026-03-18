"""
Generate a STAC Item JSON for a Nested-EAGLE forecast run.

Called after inference writes the NetCDF output. Produces a STAC Item
alongside the forecast file so MPC Pro can discover and catalog it.

Usage (standalone):
  python stac_item.py --config nested_eagle.yaml

Programmatic:
  from stac_item import create_stac_item
  item_dict = create_stac_item(ic_timestamp, version, output_storage_url)
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

# Bounding box: CONUS nested inside global
# [west, south, east, north]
BBOX_GLOBAL = [-180.0, -90.0, 180.0, 90.0]

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


def create_stac_item(
    ic_timestamp: pd.Timestamp,
    version: str,
    output_storage_url: str,
) -> dict:
    """
    Build a STAC Item dict for one forecast cycle.

    Parameters
    ----------
    ic_timestamp : pd.Timestamp
        Forecast initialization time (e.g. 2026-03-18T06:00:00Z).
    version : str
        Model version string (e.g. "nested_eagle").
    output_storage_url : str
        Base URL of the output blob container, e.g.
        "https://<account>.blob.core.windows.net/nested-eagle-forecasts"

    Returns
    -------
    dict
        A STAC-compliant Item as a Python dict.
    """
    init_utc = ic_timestamp.astimezone(timezone.utc)
    folder = init_utc.strftime("%Y/%m/%d/%H")
    item_id = f"nested-eagle-{init_utc.strftime('%Y%m%d-%H')}z"

    forecast_end = init_utc + pd.Timedelta(hours=FORECAST_HOURS)

    # Asset paths
    nc_path = f"v1/{folder}/forecast.nc"
    nc_href = f"{output_storage_url.rstrip('/')}/{nc_path}"

    item = {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": item_id,
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [-180.0, -90.0],
                    [180.0, -90.0],
                    [180.0, 90.0],
                    [-180.0, 90.0],
                    [-180.0, -90.0],
                ]
            ],
        },
        "bbox": BBOX_GLOBAL,
        "properties": {
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
        },
        "collection": COLLECTION_ID,
        "links": [
            {
                "rel": "collection",
                "href": f"./collection.json",
                "type": "application/json",
            },
            {
                "rel": "parent",
                "href": f"./collection.json",
                "type": "application/json",
            },
        ],
        "assets": {
            "forecast": {
                "href": nc_href,
                "type": "application/netcdf",
                "title": "Forecast NetCDF",
                "description": (
                    f"Nested-EAGLE {FORECAST_HOURS}h forecast initialized "
                    f"at {init_utc.strftime('%Y-%m-%d %H:%M')} UTC"
                ),
                "roles": ["data"],
            },
        },
    }

    return item


def write_stac_item(
    ic_timestamp: pd.Timestamp,
    version: str,
    output_storage_url: str,
) -> str:
    """
    Create a STAC Item and write it to disk next to the forecast file.

    Returns the path to the written JSON file.
    """
    item = create_stac_item(ic_timestamp, version, output_storage_url)

    folder = ic_timestamp.strftime("%Y/%m/%d/%H")
    output_dir = f"{version}/inference/{folder}"
    os.makedirs(output_dir, exist_ok=True)

    item_path = os.path.join(output_dir, "stac_item.json")
    with open(item_path, "w") as f:
        json.dump(item, f, indent=2)

    print(f"STAC Item written: {item_path}")
    return item_path


def run(version: str, output_storage_url: str):
    """Generate a STAC Item for the current NRT cycle."""
    ic_timestamp = utils.get_nrt_timestamp()
    write_stac_item(ic_timestamp, version, output_storage_url)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate STAC Item for a Nested-EAGLE forecast"
    )
    parser.add_argument("--config", required=True, help="Path to config YAML")
    parser.add_argument(
        "--output-storage-url",
        default="https://STORAGE_ACCOUNT.blob.core.windows.net/nested-eagle-forecasts",
        help="Base URL of the forecast output blob container",
    )
    args = parser.parse_args()

    config = utils.load_config(args.config)
    version = config["version"]

    run(version=version, output_storage_url=args.output_storage_url)
