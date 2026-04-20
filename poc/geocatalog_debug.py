"""
Debug GeoCatalog ingestion — check run status, create ingestion, start runs.

Gives full error details that the portal UI doesn't show.

Usage:
  # Check existing ingestion runs (see why it failed)
  python geocatalog_debug.py --check

  # Create a new ingestion + start a run
  python geocatalog_debug.py --ingest
"""

import argparse
import json
import requests
from azure.identity import AzureCliCredential
from pprint import pprint

# --- Configuration (update these) ---
GEOCATALOG_URI = "https://nestedeagle.ftdcdtg2bahpanfd.eastus.geocatalog.spatio.azure.com"
COLLECTION_ID = "nested-eagle"
CATALOG_HREF = "https://eagleforecasts.blob.core.windows.net/nested-eagle/stac/collection.json"
API_VERSION = "2025-04-30-preview"
MPCPRO_APP_ID = "https://geocatalog.spatio.azure.com"


def get_token():
    credential = AzureCliCredential()
    return credential.get_token(f"{MPCPRO_APP_ID}/.default").token


def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def check_ingestions(token):
    """List all ingestions and their runs, printing full error details."""
    print("=== Listing ingestions ===")
    url = f"{GEOCATALOG_URI}/inma/collections/{COLLECTION_ID}/ingestions"
    resp = requests.get(url, headers=headers(token), params={"api-version": API_VERSION})
    print(f"Status: {resp.status_code}")
    data = resp.json()
    pprint(data)

    # For each ingestion, list its runs
    ingestions = data.get("value", data) if isinstance(data, dict) else data
    if isinstance(ingestions, dict):
        ingestions = ingestions.get("value", [])

    for ing in ingestions:
        ing_id = ing.get("ingestionId", ing.get("id", "unknown"))
        print(f"\n=== Runs for ingestion {ing_id} ===")
        runs_url = f"{GEOCATALOG_URI}/inma/collections/{COLLECTION_ID}/ingestions/{ing_id}/runs"
        runs_resp = requests.get(runs_url, headers=headers(token), params={"api-version": API_VERSION})
        print(f"Status: {runs_resp.status_code}")
        pprint(runs_resp.json())


def create_ingestion_and_run(token):
    """Create a new bulk ingestion and start a run."""
    # Step 1: Create ingestion
    print("=== Creating ingestion ===")
    url = f"{GEOCATALOG_URI}/inma/collections/{COLLECTION_ID}/ingestions"
    body = {
        "importType": "StaticCatalog",
        "sourceCatalogUrl": CATALOG_HREF,
        "skipExistingItems": True,
        "keepOriginalAssets": False,
    }
    resp = requests.post(url, json=body, headers=headers(token), params={"api-version": API_VERSION})
    print(f"Status: {resp.status_code}")
    pprint(resp.json())

    if resp.status_code not in (200, 201):
        print(f"\nFailed to create ingestion: {resp.text}")
        return

    ingestion_id = resp.json().get("ingestionId")
    print(f"\nIngestion ID: {ingestion_id}")

    # Step 2: Start a run
    print("\n=== Starting run ===")
    runs_url = f"{GEOCATALOG_URI}/inma/collections/{COLLECTION_ID}/ingestions/{ingestion_id}/runs"
    run_resp = requests.post(runs_url, headers=headers(token), params={"api-version": API_VERSION})
    print(f"Status: {run_resp.status_code}")
    pprint(run_resp.json())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Debug GeoCatalog ingestion")
    parser.add_argument("--check", action="store_true", help="Check existing ingestion runs")
    parser.add_argument("--ingest", action="store_true", help="Create new ingestion + start run")
    args = parser.parse_args()

    token = get_token()

    if args.check:
        check_ingestions(token)
    elif args.ingest:
        create_ingestion_and_run(token)
    else:
        print("Use --check to inspect existing runs, or --ingest to create a new one")
