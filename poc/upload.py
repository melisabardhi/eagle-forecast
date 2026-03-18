"""
Upload forecast outputs and STAC metadata to Azure Blob Storage.

Uploads both raw and post-processed forecast NetCDFs, STAC Item JSONs,
and the STAC Collection JSON to the output blob container so MPC Pro's
GeoCatalog can discover and ingest them.

Blob layout:
  data/raw/{YYYY}/{MM}/{DD}/{HH}/forecast.nc
  data/postprocessed/{YYYY}/{MM}/{DD}/{HH}/global.nc
  data/postprocessed/{YYYY}/{MM}/{DD}/{HH}/conus.nc
  stac/collection.json
  stac/items/{YYYY}/{MM}/{DD}/{HH}/raw.json
  stac/items/{YYYY}/{MM}/{DD}/{HH}/postprocessed.json

Usage (standalone):
  python upload.py --config nested_eagle.yaml

Programmatic:
  from upload import upload_forecast
  upload_forecast(version, output_storage_account, output_container)
"""

import argparse
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


def _upload_if_exists(container_client, local_path: str, blob_path: str):
    """Upload a file if it exists locally, otherwise warn."""
    if os.path.exists(local_path):
        upload_file(container_client, local_path, blob_path)
    else:
        print(f"  WARNING: {local_path} not found, skipping")


def upload_forecast(
    version: str,
    storage_account: str,
    container: str,
):
    """
    Upload all forecast outputs + STAC metadata to blob storage.

    Expects local files produced by inference.py + stac_item.py:
      {version}/inference/{folder}/forecast.nc          (raw)
      {version}/postprocessed/{folder}/global.nc        (post-processed)
      {version}/postprocessed/{folder}/conus.nc         (post-processed)
      {version}/stac/items/{folder}/raw.json            (STAC)
      {version}/stac/items/{folder}/postprocessed.json  (STAC)
    """
    ic_timestamp = utils.get_nrt_timestamp()
    folder = ic_timestamp.strftime("%Y/%m/%d/%H")

    container_client = get_blob_container_client(storage_account, container)

    # --- Data files ---
    # Raw forecast
    raw_local = f"{version}/inference/{folder}/forecast.nc"
    _upload_if_exists(container_client, raw_local, f"data/raw/{folder}/forecast.nc")

    # Post-processed: global + CONUS
    pp_local_dir = f"{version}/postprocessed/{folder}"
    _upload_if_exists(
        container_client,
        os.path.join(pp_local_dir, "global.nc"),
        f"data/postprocessed/{folder}/global.nc",
    )
    _upload_if_exists(
        container_client,
        os.path.join(pp_local_dir, "conus.nc"),
        f"data/postprocessed/{folder}/conus.nc",
    )

    # --- STAC metadata (separate folder for GeoCatalog ingestion) ---
    stac_local_dir = f"{version}/stac/items/{folder}"
    _upload_if_exists(
        container_client,
        os.path.join(stac_local_dir, "raw.json"),
        f"stac/items/{folder}/raw.json",
    )
    _upload_if_exists(
        container_client,
        os.path.join(stac_local_dir, "postprocessed.json"),
        f"stac/items/{folder}/postprocessed.json",
    )

    # STAC Collection (always overwrite to keep current)
    collection_local = os.path.join(os.path.dirname(__file__), "stac_collection.json")
    if os.path.exists(collection_local):
        upload_file(container_client, collection_local, "stac/collection.json")

    print(f"Upload complete for forecast cycle {folder}")


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
