"""
Post-process Nested-EAGLE raw forecast into separate global and CONUS files.

The raw forecast from anemoi-inference is written on a combined unstructured
grid where the HRRR 6km CONUS nodes are nested inside the GFS 0.25° global
nodes (a single 'values' dimension). This script splits the raw output back
into two separate NetCDF files:

  1. global.nc  — GFS grid (0.25° lat-lon, global)
  2. conus.nc   — HRRR grid (6km, CONUS)

Each file is written with CF-compliant metadata and zlib compression.

Usage (standalone):
  python postproc.py --config nested_eagle.yaml

Programmatic:
  from postproc import postprocess_forecast
  postprocess_forecast(version, grid_file)
"""

import argparse
import os
import sys

import numpy as np
import xarray as xr

import utils

# --- CF standard names for model variables ---
# Maps short model variable names to (CF standard_name, units)
CF_ATTRS = {
    "gh": ("geopotential_height", "m"),
    "t": ("air_temperature", "K"),
    "u": ("eastward_wind", "m s-1"),
    "v": ("northward_wind", "m s-1"),
    "w": ("lagrangian_tendency_of_air_pressure", "Pa s-1"),
    "q": ("specific_humidity", "kg kg-1"),
    "sp": ("surface_air_pressure", "Pa"),
    "u10": ("eastward_wind", "m s-1"),
    "v10": ("northward_wind", "m s-1"),
    "t2m": ("air_temperature", "K"),
    "t_surface": ("surface_temperature", "K"),
    "sh2": ("specific_humidity", "kg kg-1"),
    "lsm": ("land_binary_mask", "1"),
    "orog": ("surface_altitude", "m"),
}

# Variables that are on pressure levels vs single-level (surface)
PRESSURE_LEVEL_VARS = {"gh", "t", "u", "v", "w", "q"}
SURFACE_VARS = {"sp", "u10", "v10", "t2m", "t_surface", "sh2", "lsm", "orog"}

# Encoding for compressed NetCDF output
ENCODING_DEFAULTS = {
    "zlib": True,
    "complevel": 4,
    "shuffle": True,
}


def _get_grid_split_index(ds, grid_file):
    """
    Determine where to split the 'values' dimension into global vs CONUS.

    The HRRR 6km grid file tells us how many CONUS nodes there are.
    In Anemoi's nested-cutout approach, the CONUS nodes come first in the
    values dimension (the cutout dataset), followed by the global nodes.

    Returns (n_conus, n_global) as a tuple.
    """
    grid = xr.open_dataset(grid_file)
    n_conus = grid.sizes.get("x", 0) * grid.sizes.get("y", 0)
    if n_conus == 0:
        # Try alternative dimension names
        for dim in grid.dims:
            if "cell" in dim or "ncells" in dim:
                n_conus = grid.sizes[dim]
                break
    grid.close()

    n_total = ds.sizes["values"]
    n_global = n_total - n_conus

    if n_global <= 0:
        raise ValueError(
            f"Grid split failed: total values={n_total}, CONUS nodes={n_conus}. "
            f"Check grid_file={grid_file}."
        )

    return n_conus, n_global


def _add_cf_attrs(ds):
    """Add CF standard_name and units to variables where known."""
    for var_name in ds.data_vars:
        # Strip level suffix if present (e.g., "t_500" -> "t")
        base_name = var_name.split("_")[0] if "_" in var_name else var_name
        if base_name in CF_ATTRS:
            std_name, units = CF_ATTRS[base_name]
            ds[var_name].attrs.setdefault("standard_name", std_name)
            ds[var_name].attrs.setdefault("units", units)
    return ds


def _build_encoding(ds):
    """Build per-variable encoding dict for compressed NetCDF output."""
    encoding = {}
    for var_name in ds.data_vars:
        encoding[var_name] = dict(ENCODING_DEFAULTS)
    return encoding


def _write_subset(ds, indices, output_path, global_attrs):
    """
    Select a subset of the values dimension, add CF attrs, and write.
    """
    subset = ds.isel(values=indices)
    subset = _add_cf_attrs(subset)
    subset.attrs.update(global_attrs)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    encoding = _build_encoding(subset)
    subset.to_netcdf(output_path, encoding=encoding)
    print(f"  Written: {output_path}")

    return output_path


def postprocess_forecast(
    version: str,
    grid_file: str = "config/hrrr_06km.nc",
):
    """
    Split raw forecast into global.nc and conus.nc.

    Parameters
    ----------
    version : str
        Model version string, used for directory paths.
    grid_file : str
        Path to the HRRR 6km grid file (used to determine split point).
    """
    ic_timestamp = utils.get_nrt_timestamp()
    folder = ic_timestamp.strftime("%Y/%m/%d/%H")

    raw_path = f"{version}/inference/{folder}/forecast.nc"
    output_dir = f"{version}/postprocessed/{folder}"

    if not os.path.exists(raw_path):
        print(f"ERROR: Raw forecast not found: {raw_path}")
        sys.exit(1)

    print(f"Post-processing {raw_path}...")
    ds = xr.open_dataset(raw_path)

    n_conus, n_global = _get_grid_split_index(ds, grid_file)
    print(f"  Grid split: {n_conus} CONUS nodes + {n_global} global nodes = {n_conus + n_global} total")

    conus_indices = np.arange(0, n_conus)
    global_indices = np.arange(n_conus, n_conus + n_global)

    # Global attributes for CF compliance
    base_attrs = {
        "Conventions": "CF-1.8",
        "institution": "NOAA/EPIC",
        "source": f"Nested-EAGLE AI weather model ({version})",
        "references": "ECMWF Anemoi framework",
        "forecast_reference_time": ic_timestamp.isoformat(),
        "forecast_horizon_hours": 240,
    }

    # Write global forecast
    global_attrs = {**base_attrs, "title": "Nested-EAGLE Global Forecast (GFS grid, 0.25°)"}
    _write_subset(ds, global_indices, os.path.join(output_dir, "global.nc"), global_attrs)

    # Write CONUS forecast
    conus_attrs = {**base_attrs, "title": "Nested-EAGLE CONUS Forecast (HRRR grid, 6km)"}
    _write_subset(ds, conus_indices, os.path.join(output_dir, "conus.nc"), conus_attrs)

    ds.close()
    print(f"Post-processing complete: {output_dir}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Post-process Nested-EAGLE forecast into global + CONUS files"
    )
    parser.add_argument("--config", required=True, help="Path to config YAML")
    parser.add_argument(
        "--grid-file",
        default="config/hrrr_06km.nc",
        help="Path to HRRR 6km grid file (default: config/hrrr_06km.nc)",
    )
    args = parser.parse_args()

    config = utils.load_config(args.config)
    version = config["version"]

    postprocess_forecast(version=version, grid_file=args.grid_file)
