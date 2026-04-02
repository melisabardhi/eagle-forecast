"""
Ingest STAC Items into Microsoft Planetary Computer Pro GeoCatalog.

This integrates with the MPC Pro API to properly add STAC items to a collection,
following the workflow from: 
https://learn.microsoft.com/en-us/azure/planetary-computer/add-stac-item-to-collection

Usage:
  python stac_ingestion.py --config nested_eagle.yaml --geocatalog-url https://your-geocatalog.com
"""

import argparse
import json
import time
import datetime
from typing import Dict, List, Optional

import requests
import azure.identity
import pandas as pd

import utils
from stac_item import create_raw_stac_item, create_postprocessed_stac_item, COLLECTION_ID


class STACIngestionError(Exception):
    """Custom exception for STAC ingestion failures."""
    pass


class MpcProSTACIngestor:
    """
    Handles STAC item ingestion into Microsoft Planetary Computer Pro GeoCatalog.
    """
    
    def __init__(self, geocatalog_url: str, collection_id: str = COLLECTION_ID):
        """
        Initialize the ingestion client.
        
        Args:
            geocatalog_url: Base URL to your MPC Pro GeoCatalog (no trailing slash)
            collection_id: STAC collection ID to add items to
        """
        self.geocatalog_url = geocatalog_url.rstrip("/")
        self.collection_id = collection_id
        self.api_version = "2025-04-30-preview"
        
        # Get authentication token
        self.credential = azure.identity.AzureCliCredential()
        self._refresh_token()
    
    def _refresh_token(self):
        """Get a fresh access token for authentication."""
        token = self.credential.get_token("https://geocatalog.spatio.azure.com")
        self.headers = {
            "Authorization": f"Bearer {token.token}",
            "Content-Type": "application/json"
        }
    
    def create_stac_item_collection(self, items: List[Dict]) -> Dict:
        """
        Create a STAC ItemCollection from individual STAC items.
        
        Args:
            items: List of STAC Item dictionaries
            
        Returns:
            STAC ItemCollection dictionary
        """
        return {
            "type": "FeatureCollection",
            "features": items
        }
    
    def ingest_items(self, items: List[Dict], monitor: bool = True) -> Dict:
        """
        Ingest STAC items into the collection.
        
        Args:
            items: List of STAC Item dictionaries
            monitor: Whether to monitor ingestion status until completion
            
        Returns:
            Dictionary with ingestion status and details
        """
        # Ensure collection property matches target collection
        for item in items:
            item["collection"] = self.collection_id
        
        # Create ItemCollection
        item_collection = self.create_stac_item_collection(items)
        
        # Submit to ingestion API
        url = f"{self.geocatalog_url}/stac/collections/{self.collection_id}/items"
        params = {"api-version": self.api_version}
        
        print(f"Submitting {len(items)} STAC items to collection '{self.collection_id}'...")
        
        response = requests.post(
            url,
            headers=self.headers,
            params=params,
            json=item_collection
        )
        
        if response.status_code == 202:
            print(f"✓ Items accepted for ingestion (status: {response.status_code})")
            location = response.headers.get("location")
            
            if monitor and location:
                return self._monitor_ingestion(location)
            else:
                return {
                    "status": "accepted",
                    "location": location,
                    "response": response.json() if response.content else None
                }
        else:
            error_msg = f"Ingestion failed (status: {response.status_code})"
            try:
                error_details = response.json()
                error_msg += f"\nDetails: {error_details}"
            except:
                error_msg += f"\nResponse: {response.text}"
            
            raise STACIngestionError(error_msg)
    
    def _monitor_ingestion(self, location: str, timeout_minutes: int = 10) -> Dict:
        """
        Monitor ingestion status until completion.
        
        Args:
            location: URL to poll for ingestion status
            timeout_minutes: Maximum time to wait for completion
            
        Returns:
            Final ingestion status
        """
        print(f"Monitoring ingestion status: {location}")
        start_time = datetime.datetime.now()
        timeout = datetime.timedelta(minutes=timeout_minutes)
        
        while True:
            response = requests.get(
                location, 
                headers={"Authorization": self.headers["Authorization"]}
            )
            
            if response.status_code != 200:
                raise STACIngestionError(f"Failed to check status: {response.status_code}")
            
            status_info = response.json()
            status = status_info["status"]
            timestamp = datetime.datetime.now().isoformat()
            
            print(f"[{timestamp}] Ingestion status: {status}")
            
            if status not in {"Pending", "Running"}:
                if status == "Completed":
                    print("✓ Ingestion completed successfully!")
                else:
                    print(f"✗ Ingestion failed with status: {status}")
                return status_info
            
            # Check timeout
            if datetime.datetime.now() - start_time > timeout:
                print(f"⚠ Timeout after {timeout_minutes} minutes, but ingestion may still be running")
                return status_info
            
            time.sleep(5)
    
    def verify_items(self, item_ids: List[str]) -> Dict:
        """
        Verify that items were successfully ingested.
        
        Args:
            item_ids: List of STAC item IDs to check
            
        Returns:
            Dictionary with verification results
        """
        url = f"{self.geocatalog_url}/stac/collections/{self.collection_id}/items"
        params = {"api-version": self.api_version}
        
        response = requests.get(url, headers=self.headers, params=params)
        
        if response.status_code != 200:
            raise STACIngestionError(f"Failed to retrieve items: {response.status_code}")
        
        items_response = response.json()
        ingested_ids = {item["id"] for item in items_response.get("features", [])}
        
        found_ids = []
        missing_ids = []
        
        for item_id in item_ids:
            if item_id in ingested_ids:
                found_ids.append(item_id)
            else:
                missing_ids.append(item_id)
        
        print(f"Verification: {len(found_ids)}/{len(item_ids)} items found in collection")
        
        return {
            "total_items": len(items_response.get("features", [])),
            "found_ids": found_ids,
            "missing_ids": missing_ids,
            "all_ingested": len(missing_ids) == 0
        }


def ingest_forecast_stac_items(
    ic_timestamp: pd.Timestamp,
    version: str,
    output_storage_url: str,
    geocatalog_url: str,
    collection_id: str = COLLECTION_ID
) -> Dict:
    """
    Create and ingest STAC items for a forecast run.
    
    Args:
        ic_timestamp: Forecast initialization timestamp
        version: Pipeline version identifier
        output_storage_url: Base URL for forecast data storage
        geocatalog_url: MPC Pro GeoCatalog URL
        collection_id: Target STAC collection ID
        
    Returns:
        Ingestion results
    """
    # Create STAC items
    print(f"Creating STAC items for forecast: {ic_timestamp.strftime('%Y-%m-%d %H:%M')} UTC")
    
    raw_item = create_raw_stac_item(ic_timestamp, version, output_storage_url)
    postprocessed_item = create_postprocessed_stac_item(ic_timestamp, version, output_storage_url)
    
    items = [raw_item, postprocessed_item]
    item_ids = [item["id"] for item in items]
    
    # Initialize ingestion client
    ingestor = MpcProSTACIngestor(geocatalog_url, collection_id)
    
    try:
        # Ingest items
        ingestion_result = ingestor.ingest_items(items, monitor=True)
        
        # Verify ingestion if successful
        if ingestion_result.get("status") == "Completed":
            verification_result = ingestor.verify_items(item_ids)
            ingestion_result["verification"] = verification_result
            
            if verification_result["all_ingested"]:
                print("✓ All items successfully ingested and verified!")
            else:
                print(f"⚠ Some items missing: {verification_result['missing_ids']}")
        
        return ingestion_result
        
    except STACIngestionError as e:
        print(f"✗ Ingestion failed: {e}")
        return {"status": "failed", "error": str(e)}


def run(version: str, output_storage_url: str, geocatalog_url: str):
    """Ingest STAC items for the current NRT cycle."""
    ic_timestamp = utils.get_nrt_timestamp()
    
    return ingest_forecast_stac_items(
        ic_timestamp=ic_timestamp,
        version=version,
        output_storage_url=output_storage_url,
        geocatalog_url=geocatalog_url
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingest STAC Items for a Nested-EAGLE forecast into MPC Pro GeoCatalog"
    )
    parser.add_argument("--config", required=True, help="Path to config YAML")
    parser.add_argument("--geocatalog-url", required=True, 
                        help="URL to your MPC Pro GeoCatalog (e.g., https://your-geocatalog.com)")
    parser.add_argument("--collection-id", default=COLLECTION_ID,
                        help=f"STAC collection ID (default: {COLLECTION_ID})")
    
    args = parser.parse_args()
    
    config = utils.load_config(args.config)
    version = config["version"]
    output_storage_url = config.get(
        "output_storage_url",
        "https://STORAGE_ACCOUNT.blob.core.windows.net/nested-eagle-forecasts",
    )
    
    result = run(
        version=version,
        output_storage_url=output_storage_url,
        geocatalog_url=args.geocatalog_url
    )
    
    print(f"\nFinal result: {result}")