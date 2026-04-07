#!/usr/bin/env python3
"""
Validation script to test GeoCatalog APIM setup.

This script verifies that the APIM configuration is working correctly
by testing various endpoints and scenarios.
"""

import click
import requests
import json
import sys
from typing import Dict, List


class GeoCatalogAPIMValidator:
    """Test APIM setup for GeoCatalog proxy."""
    
    def __init__(self, apim_gateway_url: str, subscription_key: str = None):
        self.gateway_url = apim_gateway_url.rstrip('/')
        self.subscription_key = subscription_key
        self.session = requests.Session()
        
        if subscription_key:
            self.session.headers['Ocp-Apim-Subscription-Key'] = subscription_key
            
    def test_blocked_endpoints(self) -> Dict[str, bool]:
        """Test that discovery endpoints return 404."""
        print("🔒 Testing blocked endpoints...")
        
        blocked_endpoints = [
            "/",
            "/stac/collections", 
            "/sas/sign"
        ]
        
        results = {}
        for endpoint in blocked_endpoints:
            try:
                response = self.session.get(f"{self.gateway_url}{endpoint}")
                success = response.status_code == 404
                results[endpoint] = success
                status = "✅" if success else "❌"
                print(f"  {status} {endpoint}: {response.status_code}")
            except Exception as e:
                results[endpoint] = False
                print(f"  ❌ {endpoint}: Error - {e}")
                
        return results
        
    def test_collection_access(self, allowed_collections: List[str], 
                             unauthorized_collection: str = "unauthorized-collection") -> Dict[str, bool]:
        """Test collection-level access controls."""
        print("🔐 Testing collection access controls...")
        
        results = {}
        
        # Test allowed collections
        for collection in allowed_collections:
            endpoint = f"/stac/collections/{collection}"
            try:
                response = self.session.get(f"{self.gateway_url}{endpoint}")
                # Should be 200 (valid) or 404 (collection doesn't exist), but not 403
                success = response.status_code != 403
                results[f"allowed_{collection}"] = success
                status = "✅" if success else "❌"
                print(f"  {status} Allowed collection {collection}: {response.status_code}")
            except Exception as e:
                results[f"allowed_{collection}"] = False
                print(f"  ❌ Allowed collection {collection}: Error - {e}")
                
        # Test unauthorized collection  
        endpoint = f"/stac/collections/{unauthorized_collection}"
        try:
            response = self.session.get(f"{self.gateway_url}{endpoint}")
            success = response.status_code == 403
            results["unauthorized_collection"] = success
            status = "✅" if success else "❌"
            print(f"  {status} Unauthorized collection: {response.status_code}")
        except Exception as e:
            results["unauthorized_collection"] = False
            print(f"  ❌ Unauthorized collection: Error - {e}")
            
        return results
        
    def test_search_validation(self, allowed_collections: List[str]) -> Dict[str, bool]:
        """Test search endpoint collection validation.""" 
        print("🔍 Testing search validation...")
        
        results = {}
        
        # Test GET search with allowed collections
        collections_param = ",".join(allowed_collections[:2])  # Test first 2
        try:
            response = self.session.get(
                f"{self.gateway_url}/stac/search",
                params={"collections": collections_param, "limit": 1}
            )
            success = response.status_code != 403
            results["get_search_allowed"] = success
            status = "✅" if success else "❌"
            print(f"  {status} GET search with allowed collections: {response.status_code}")
        except Exception as e:
            results["get_search_allowed"] = False
            print(f"  ❌ GET search with allowed collections: Error - {e}")
            
        # Test GET search with unauthorized collection
        try:
            response = self.session.get(
                f"{self.gateway_url}/stac/search",
                params={"collections": "unauthorized-collection", "limit": 1}
            )
            success = response.status_code == 403
            results["get_search_unauthorized"] = success
            status = "✅" if success else "❌"
            print(f"  {status} GET search with unauthorized collection: {response.status_code}")
        except Exception as e:
            results["get_search_unauthorized"] = False
            print(f"  ❌ GET search with unauthorized collection: Error - {e}")
            
        # Test POST search with allowed collections
        search_body = {
            "collections": allowed_collections[:1],  # Test first collection
            "limit": 1
        }
        try:
            response = self.session.post(
                f"{self.gateway_url}/stac/search",
                json=search_body,
                headers={"Content-Type": "application/json"}
            )
            success = response.status_code != 403
            results["post_search_allowed"] = success
            status = "✅" if success else "❌"
            print(f"  {status} POST search with allowed collections: {response.status_code}")
        except Exception as e:
            results["post_search_allowed"] = False
            print(f"  ❌ POST search with allowed collections: Error - {e}")
            
        # Test POST search with unauthorized collection
        search_body = {
            "collections": ["unauthorized-collection"],
            "limit": 1
        }
        try:
            response = self.session.post(
                f"{self.gateway_url}/stac/search",
                json=search_body,
                headers={"Content-Type": "application/json"}
            )
            success = response.status_code == 403
            results["post_search_unauthorized"] = success
            status = "✅" if success else "❌"
            print(f"  {status} POST search with unauthorized collection: {response.status_code}")
        except Exception as e:
            results["post_search_unauthorized"] = False
            print(f"  ❌ POST search with unauthorized collection: Error - {e}")
            
        return results
        
    def test_sas_token_access(self, allowed_collections: List[str]) -> Dict[str, bool]:
        """Test SAS token endpoint access controls."""
        print("🎫 Testing SAS token access...")
        
        results = {}
        
        # Test allowed collection SAS token
        if allowed_collections:
            collection = allowed_collections[0]
            try:
                response = self.session.get(f"{self.gateway_url}/sas/token/{collection}")
                success = response.status_code != 403
                results["sas_allowed"] = success
                status = "✅" if success else "❌"
                print(f"  {status} SAS token for allowed collection {collection}: {response.status_code}")
            except Exception as e:
                results["sas_allowed"] = False
                print(f"  ❌ SAS token for allowed collection: Error - {e}")
                
        # Test unauthorized collection SAS token
        try:
            response = self.session.get(f"{self.gateway_url}/sas/token/unauthorized-collection")
            success = response.status_code == 403
            results["sas_unauthorized"] = success
            status = "✅" if success else "❌"  
            print(f"  {status} SAS token for unauthorized collection: {response.status_code}")
        except Exception as e:
            results["sas_unauthorized"] = False
            print(f"  ❌ SAS token for unauthorized collection: Error - {e}")
            
        return results
        
    def run_full_validation(self, allowed_collections: List[str]) -> bool:
        """Run all validation tests."""
        print(f"🧪 Validating APIM setup for gateway: {self.gateway_url}")
        print(f"📝 Allowed collections: {', '.join(allowed_collections)}")
        if self.subscription_key:
            print(f"🔑 Using subscription key: {self.subscription_key[:8]}...")
        print()
        
        all_results = {}
        
        # Run all tests
        all_results.update(self.test_blocked_endpoints())
        all_results.update(self.test_collection_access(allowed_collections))
        all_results.update(self.test_search_validation(allowed_collections))
        all_results.update(self.test_sas_token_access(allowed_collections))
        
        # Summary
        total_tests = len(all_results)
        passed_tests = sum(all_results.values()) 
        failed_tests = total_tests - passed_tests
        
        print("\n📊 Validation Summary:")
        print(f"  Total tests: {total_tests}")
        print(f"  Passed: {passed_tests} ✅")
        print(f"  Failed: {failed_tests} ❌")
        
        if failed_tests == 0:
            print("\n🎉 All tests passed! Your APIM setup is working correctly.")
            return True
        else:
            print(f"\n⚠️  {failed_tests} tests failed. Please check your APIM configuration.")
            
            failed_test_names = [name for name, result in all_results.items() if not result]
            print("Failed tests:")
            for test_name in failed_test_names:
                print(f"  - {test_name}")
            
            return False


@click.command()
@click.option('--gateway-url', required=True, 
              help='APIM gateway URL (e.g., https://your-apim.azure-api.net)')
@click.option('--allowed-collections', required=True,
              help='Comma-separated list of collections that should be allowed')
@click.option('--subscription-key', 
              help='APIM subscription key (if using subscription-based access)')
def main(gateway_url: str, allowed_collections: str, subscription_key: str = None):
    """
    Validate GeoCatalog APIM setup.
    
    This script tests that your APIM configuration is working correctly by:
    - Verifying that discovery endpoints are blocked (404)
    - Testing collection-level access controls (403 for unauthorized)
    - Validating search endpoint collection filtering
    - Checking SAS token access restrictions
    
    Examples:
    
    Basic validation:
    python validate_apim_setup.py \\
        --gateway-url "https://my-apim.azure-api.net" \\
        --allowed-collections "sentinel-2-l2a,landsat-8-c2-l2"
        
    With subscription key:
    python validate_apim_setup.py \\
        --gateway-url "https://my-apim.azure-api.net" \\
        --allowed-collections "sentinel-2-l2a" \\
        --subscription-key "your-subscription-key"
    """
    collections_list = [c.strip() for c in allowed_collections.split(',')]
    
    validator = GeoCatalogAPIMValidator(gateway_url, subscription_key)
    success = validator.run_full_validation(collections_list)
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()