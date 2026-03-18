"""
Upload forecast outputs and STAC metadata to Azure Blob Storage.

Uploads the forecast NetCDF, STAC Item JSON, and (on first run) the
STAC Collection JSON to the output blob container so MPC Pro can
discover and ingest them.

Usage (standalone):
  python upload.py --config nested_eagle.yaml

Programmatic:
  from upload import upload_forecast
  upload_forecast(version, output_storage_account, output_container)
"""

import argparse
import json
import os
import sys

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

import utils


def get_blob_container_client(storage_account: str, container: str):
    """Create an authenticated blob container client using Managed Identity."""
    credential = DefaultAzureCredential()
    account_url = f"https://{storage_account}.blob.core.windows.net"
    blob_service = BlobServiceClient(account_url, credential=credential)
    return blob_service.get_container_client(container)


def upload_file(container_client, local_path: str, blob_path: str):
    """Upload a single file to blob storage, overwriting if exists."""
    print(f"  Uploading {local_path} -> {blob_path}")
    with open(local_path, "rb") as f:
        container_client.upload_blob(name=blob_path, data=f, overwrite=True)


def upload_forecast(
    version: str,
    storage_account: str,
    container: str,
):
    """
    Upload forecast NetCDF + STAC Item + Collection to blob storage.

    Expects the following local files (produced by inference.py + stac_item.py):
      {version}/inference/{YYYY}/{MM}/{DD}/{HH}/forecast.nc
      {version}/inference/{YYYY}/{MM}/{DD}/{HH}/stac_item.json

    Uploads to blob paths:
      v1/{YYYY}/{MM}/{DD}/{HH}/forecast.nc
      v1/{YYYY}/{MM}/{DD}/{HH}/stac_item.json
      v1/collection.json   (uploaded once, overwritten each run)
    """
    ic_timestamp = utils.get_nrt_timestamp()
    folder = ic_timestamp.strftime("%Y/%m/%d/%H")

    local_dir = f"{version}/inference/{folder}"
    blob_prefix = f"v1/{folder}"

    container_client = get_blob_container_client(storage_account, container)

    # Upload forecast NetCDF
    nc_local = os.path.join(local_dir, "forecast.nc")
    if os.path.exists(nc_local):
        upload_file(container_client, nc_local, f"{blob_prefix}/forecast.nc")
    else:
        print(f"  WARNING: {nc_local} not found, skipping NetCDF upload")

    # Upload STAC Item JSON
    stac_local = os.path.join(local_dir, "stac_item.json")
    if os.path.exists(stac_local):
        upload_file(container_client, stac_local, f"{blob_prefix}/stac_item.json")
    else:
        print(f"  WARNING: {stac_local} not found, skipping STAC Item upload")

    # Upload STAC Collection (always overwrite — keeps it current)
    collection_local = os.path.join(os.path.dirname(__file__), "stac_collection.json")
    if os.path.exists(collection_local):
        upload_file(container_client, collection_local, "v1/collection.json")

    print(f"Upload complete: {blob_prefix}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Upload Nested-EAGLE forecast + STAC to blob storage"
    )
    parser.add_argument("--config", required=True, help="Path to config YAML")
    args = parser.parse_args()

    config = utils.load_config(args.config)
    version = config["version"]
    storage_account = config.get("output_storage_account", "<FORECAST_STORAGE_ACCOUNT>")
    container = config.get("output_container", "nested-eagle-forecasts")

    upload_forecast(
        version=version,
        storage_account=storage_account,
        container=container,
    )
