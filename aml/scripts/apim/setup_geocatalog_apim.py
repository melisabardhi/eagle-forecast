#!/usr/bin/env python3
"""
Azure APIM GeoCatalog Proxy Setup Script

This script automates the setup of Azure API Management to proxy GeoCatalog requests
with authentication and collection-level RBAC as described in:
https://gist.github.com/ghidalgo3/ce6cac6a1cd3a324e77b064e48da05ca

Requirements:
- Azure CLI logged in with appropriate permissions
- Python packages: azure-mgmt-apimanagement, azure-identity, click
"""

import json
import logging
from typing import List, Dict, Optional
import click
from azure.identity import AzureCliCredential
from azure.mgmt.apimanagement import ApiManagementClient
from azure.mgmt.apimanagement.models import (
    ApiCreateOrUpdateParameter,
    ApiType,
    ApiReleaseContract,
    OperationContract,
    ApiOperationPolicy,
    NamedValueCreateContract,
    ProductContract,
    ProductPolicy,
    SubscriptionCreateParameters
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class GeoCatalogAPIMSetup:
    """Setup Azure APIM for GeoCatalog proxy with authentication and RBAC."""
    
    def __init__(self, subscription_id: str, resource_group: str, apim_service_name: str):
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.apim_service_name = apim_service_name
        self.credential = AzureCliCredential()
        self.apim_client = ApiManagementClient(self.credential, subscription_id)
        
    def create_api(self, api_name: str, geocatalog_url: str, display_name: str = "GeoCatalog API") -> str:
        """Create the main GeoCatalog API in APIM."""
        logger.info(f"Creating API: {api_name}")
        
        api_params = ApiCreateOrUpdateParameter(
            display_name=display_name,
            service_url=geocatalog_url,
            path="",  # Root path
            protocols=["https"],
            subscription_required=False,
            api_type=ApiType.HTTP
        )
        
        try:
            result = self.apim_client.api.create_or_update(
                resource_group_name=self.resource_group,
                service_name=self.apim_service_name,
                api_id=api_name,
                parameters=api_params
            )
            logger.info(f"Successfully created API: {api_name}")
            return api_name
        except Exception as e:
            logger.error(f"Failed to create API: {e}")
            raise

    def create_api_operations(self, api_name: str) -> None:
        """Create all necessary operations for the GeoCatalog API."""
        logger.info("Creating API operations...")
        
        operations = [
            # Wildcard operations
            {
                "operation_id": "get-wildcard",
                "display_name": "GET Wildcard",
                "method": "GET",
                "url_template": "/*"
            },
            {
                "operation_id": "post-wildcard", 
                "display_name": "POST Wildcard",
                "method": "POST",
                "url_template": "/*"
            },
            # Collection operations for RBAC
            {
                "operation_id": "get-single-collection",
                "display_name": "Get Single Collection", 
                "method": "GET",
                "url_template": "/stac/collections/{collection_id}"
            },
            {
                "operation_id": "get-collection-items",
                "display_name": "Get Collection Items",
                "method": "GET", 
                "url_template": "/stac/collections/{collection_id}/items"
            },
            {
                "operation_id": "get-collection-subresources",
                "display_name": "Get Collection Sub-resources",
                "method": "GET",
                "url_template": "/stac/collections/{collection_id}/*"
            },
            # Search operations
            {
                "operation_id": "get-stac-search",
                "display_name": "GET Search",
                "method": "GET",
                "url_template": "/stac/search"
            },
            {
                "operation_id": "post-stac-search", 
                "display_name": "POST Search",
                "method": "POST",
                "url_template": "/stac/search"
            },
            # Block operations
            {
                "operation_id": "block-root",
                "display_name": "Block Root",
                "method": "GET", 
                "url_template": "/"
            },
            {
                "operation_id": "block-collections",
                "display_name": "Block Collections",
                "method": "GET",
                "url_template": "/stac/collections"
            },
            # SAS operations
            {
                "operation_id": "get-sas-token",
                "display_name": "GET SAS Token", 
                "method": "GET",
                "url_template": "/sas/token/{collection_id}"
            },
            {
                "operation_id": "block-sas-sign",
                "display_name": "Block SAS Sign",
                "method": "GET",
                "url_template": "/sas/sign"
            },
            # Data mosaic operations
            {
                "operation_id": "post-mosaic-register",
                "display_name": "POST Mosaic Register",
                "method": "POST", 
                "url_template": "/data/mosaic/register"
            },
            {
                "operation_id": "get-mosaic-collections",
                "display_name": "GET Mosaic Collections",
                "method": "GET",
                "url_template": "/data/mosaic/collections/{collectionId}/*"
            },
            {
                "operation_id": "post-mosaic-collections", 
                "display_name": "POST Mosaic Collections",
                "method": "POST",
                "url_template": "/data/mosaic/collections/{collectionId}/*"
            }
        ]
        
        for op in operations:
            try:
                operation_contract = OperationContract(
                    display_name=op["display_name"],
                    method=op["method"], 
                    url_template=op["url_template"]
                )
                
                self.apim_client.api_operation.create_or_update(
                    resource_group_name=self.resource_group,
                    service_name=self.apim_service_name,
                    api_id=api_name,
                    operation_id=op["operation_id"],
                    parameters=operation_contract
                )
                logger.info(f"Created operation: {op['operation_id']}")
            except Exception as e:
                logger.error(f"Failed to create operation {op['operation_id']}: {e}")
                
    def create_api_policy(self, api_name: str, geocatalog_url: str, managed_identity_client_id: str) -> None:
        """Create the API-level policy for authentication and URL rewriting."""
        logger.info("Creating API-level policy...")
        
        policy_xml = f"""
<policies>
    <inbound>
        <base />
        <authentication-managed-identity
            resource="https://geocatalog.spatio.azure.com"
            client-id="{managed_identity_client_id}" />
    </inbound>
    <backend>
        <base />
    </backend>
    <outbound>
        <base />
        <find-and-replace
            from="{geocatalog_url}"
            to="https://{self.apim_service_name}.azure-api.net" />
    </outbound>
    <on-error>
        <base />
    </on-error>
</policies>
        """.strip()
        
        try:
            self.apim_client.api_policy.create_or_update(
                resource_group_name=self.resource_group,
                service_name=self.apim_service_name,
                api_id=api_name,
                parameters={"format": "xml", "value": policy_xml}
            )
            logger.info("Successfully created API-level policy")
        except Exception as e:
            logger.error(f"Failed to create API policy: {e}")
            raise

    def create_operation_policies(self, api_name: str, allowed_collections: str) -> None:
        """Create operation-level policies for RBAC and blocking."""
        logger.info("Creating operation-level policies...")
        
        # Block policy for root and collections endpoints
        block_policy = """
<policies>
    <inbound>
        <base />
        <return-response>
            <set-status code="404" reason="Not Found" />
        </return-response>
    </inbound>
    <backend>
        <base />
    </backend>
    <outbound>
        <base />
    </outbound>
    <on-error>
        <base />
    </on-error>
</policies>
        """.strip()
        
        # Collection validation policy for path parameters
        collection_path_policy = f"""
<policies>
    <inbound>
        <base />
        <set-variable name="allowedCsv"
            value="{allowed_collections}" />
        <choose>
            <when condition='@{{
                var allowed = ((string)context
                    .Variables["allowedCsv"])
                    .Trim().ToLower();
                var collectionId = (string)context
                    .Request.MatchedParameters[
                        context.Request.MatchedParameters.ContainsKey("collection_id") ? "collection_id" : "collectionId"];
                return !collectionId.Trim()
                    .ToLower().Equals(allowed);
            }}'>
                <return-response>
                    <set-status code="403"
                        reason="Forbidden" />
                    <set-body>
                        Collection not allowed.
                    </set-body>
                </return-response>
            </when>
        </choose>
    </inbound>
    <backend>
        <base />
    </backend>
    <outbound>
        <base />
    </outbound>
    <on-error>
        <base />
    </on-error>
</policies>
        """.strip()
        
        # GET search policy for query parameter validation
        get_search_policy = f"""
<policies>
    <inbound>
        <base />
        <set-variable name="allowedCsv"
            value="{allowed_collections}" />
        <choose>
            <when condition='@{{
                var allowed = ((string)context
                    .Variables["allowedCsv"])
                    .Trim().ToLower();
                var raw = context.Request.Url.Query
                    .GetValueOrDefault("collections", "");
                if (string.IsNullOrWhiteSpace(raw)) {{
                    return true;
                }}
                foreach (var c in raw.ToLower().Split(
                    new [] {{ "," }},
                    StringSplitOptions.RemoveEmptyEntries))
                {{
                    if (!allowed.Split(',').Any(a => a.Trim().Equals(c.Trim()))) {{
                        return true;
                    }}
                }}
                return false;
            }}'>
                <return-response>
                    <set-status code="403"
                        reason="Forbidden" />
                    <set-body>
                        Collection not allowed.
                    </set-body>
                </return-response>
            </when>
        </choose>
    </inbound>
    <backend>
        <base />
    </backend>
    <outbound>
        <base />
    </outbound>
    <on-error>
        <base />
    </on-error>
</policies>
        """.strip()
        
        # POST search policy for JSON body validation  
        post_search_policy = f"""
<policies>
    <inbound>
        <base />
        <set-variable name="allowedCsv"
            value="{allowed_collections}" />
        <set-variable name="requestBody"
            value="@(context.Request.Body
                .As&lt;string&gt;(
                    preserveContent: true))" />
        <choose>
            <when condition='@{{
                var allowed = ((string)context
                    .Variables["allowedCsv"])
                    .Trim().ToLower();
                var body = (string)context
                    .Variables["requestBody"];
                var json = Newtonsoft.Json.Linq
                    .JObject.Parse(body);
                var arr = json["collections"]
                    as Newtonsoft.Json.Linq.JArray;
                if (arr == null || arr.Count == 0) {{
                    return true;
                }}
                foreach (var token in arr) {{
                    if (!allowed.Split(',').Any(a => a.Trim().ToLower().Equals(token.ToString().Trim().ToLower())))
                    {{
                        return true;
                    }}
                }}
                return false;
            }}'>
                <return-response>
                    <set-status code="403"
                        reason="Forbidden" />
                    <set-body>
                        Collection not allowed.
                    </set-body>
                </return-response>
            </when>
        </choose>
    </inbound>
    <backend>
        <base />
    </backend>
    <outbound>
        <base />
    </outbound>
    <on-error>
        <base />
    </on-error>
</policies>
        """.strip()
        
        # Apply policies to operations
        policy_mappings = {
            "block-root": block_policy,
            "block-collections": block_policy,
            "block-sas-sign": block_policy,
            "get-single-collection": collection_path_policy,
            "get-collection-items": collection_path_policy,  
            "get-collection-subresources": collection_path_policy,
            "get-sas-token": collection_path_policy,
            "get-mosaic-collections": collection_path_policy,
            "post-mosaic-collections": collection_path_policy,
            "get-stac-search": get_search_policy,
            "post-stac-search": post_search_policy,
            "post-mosaic-register": post_search_policy,
        }
        
        for operation_id, policy_xml in policy_mappings.items():
            try:
                self.apim_client.api_operation_policy.create_or_update(
                    resource_group_name=self.resource_group,
                    service_name=self.apim_service_name,
                    api_id=api_name,
                    operation_id=operation_id,
                    parameters={"format": "xml", "value": policy_xml}
                )
                logger.info(f"Created policy for operation: {operation_id}")
            except Exception as e:
                logger.error(f"Failed to create policy for operation {operation_id}: {e}")

    def create_named_value(self, name: str, value: str) -> None:
        """Create a named value in APIM."""
        logger.info(f"Creating named value: {name}")
        
        try:
            named_value = NamedValueCreateContract(
                display_name=name,
                value=value
            )
            
            self.apim_client.named_value.begin_create_or_update(
                resource_group_name=self.resource_group,
                service_name=self.apim_service_name,
                named_value_id=name,
                parameters=named_value
            )
            logger.info(f"Successfully created named value: {name}")
        except Exception as e:
            logger.error(f"Failed to create named value {name}: {e}")
            raise

    def create_products_and_subscriptions(self, api_name: str, product_configs: List[Dict]) -> None:
        """Create products with different collection access levels."""
        logger.info("Creating products and subscriptions...")
        
        for config in product_configs:
            product_name = config["name"]
            allowed_collections = config["allowed_collections"]
            
            logger.info(f"Creating product: {product_name}")
            
            # Create product
            product_contract = ProductContract(
                display_name=config.get("display_name", product_name.title()),
                subscription_required=True,
                approval_required=False,
                state="published"
            )
            
            try:
                self.apim_client.product.create_or_update(
                    resource_group_name=self.resource_group,
                    service_name=self.apim_service_name,
                    product_id=product_name,
                    parameters=product_contract
                )
                
                # Add API to product
                self.apim_client.product_api.create_or_update(
                    resource_group_name=self.resource_group,
                    service_name=self.apim_service_name,
                    product_id=product_name,
                    api_id=api_name
                )
                
                # Create named value for product collections
                named_value_name = f"{product_name}-allowed-collections"
                self.create_named_value(named_value_name, allowed_collections)
                
                # Create product policy
                product_policy_xml = f"""
<policies>
    <inbound>
        <base />
        <set-variable name="allowedCsv"
            value="{{{{{named_value_name}}}}}" />
    </inbound>
    <backend>
        <base />
    </backend>
    <outbound>
        <base />
    </outbound>
    <on-error>
        <base />
    </on-error>
</policies>
                """.strip()
                
                self.apim_client.product_policy.create_or_update(
                    resource_group_name=self.resource_group,
                    service_name=self.apim_service_name,
                    product_id=product_name,
                    parameters={"format": "xml", "value": product_policy_xml}
                )
                
                logger.info(f"Successfully created product: {product_name}")
                
            except Exception as e:
                logger.error(f"Failed to create product {product_name}: {e}")


@click.command()
@click.option('--subscription-id', required=True, help='Azure subscription ID')
@click.option('--resource-group', required=True, help='Resource group name')
@click.option('--apim-service-name', required=True, help='APIM service name')
@click.option('--api-name', default='geocatalog-api', help='API name to create')
@click.option('--geocatalog-url', required=True, help='GeoCatalog backend URL')
@click.option('--managed-identity-client-id', required=True, 
              help='Client ID of the user-assigned managed identity')
@click.option('--allowed-collections', default='sentinel-2-l2a', 
              help='Comma-separated list of allowed collections')
@click.option('--use-products', is_flag=True, 
              help='Create subscription-based products for different tiers')
@click.option('--config-file', type=click.Path(exists=True),
              help='JSON config file for advanced product configurations')
def main(subscription_id: str, resource_group: str, apim_service_name: str, 
         api_name: str, geocatalog_url: str, managed_identity_client_id: str,
         allowed_collections: str, use_products: bool, config_file: Optional[str]):
    """
    Set up Azure APIM for GeoCatalog proxy with authentication and RBAC.
    
    Example usage:
    
    Basic setup:
    python setup_geocatalog_apim.py \\
        --subscription-id "your-sub-id" \\
        --resource-group "your-rg" \\
        --apim-service-name "your-apim" \\
        --geocatalog-url "https://name.id.region.geocatalog.spatio.azure.com" \\
        --managed-identity-client-id "your-managed-identity-client-id" \\
        --allowed-collections "sentinel-2-l2a,landsat-8-c2-l2"
        
    With subscription tiers:
    python setup_geocatalog_apim.py \\
        --subscription-id "your-sub-id" \\
        --resource-group "your-rg" \\  
        --apim-service-name "your-apim" \\
        --geocatalog-url "https://name.id.region.geocatalog.spatio.azure.com" \\
        --managed-identity-client-id "your-managed-identity-client-id" \\
        --use-products \\
        --config-file product_config.json
    """
    try:
        setup = GeoCatalogAPIMSetup(subscription_id, resource_group, apim_service_name)
        
        # Create main API
        setup.create_api(api_name, geocatalog_url)
        
        # Create operations
        setup.create_api_operations(api_name)
        
        # Create API-level policy  
        setup.create_api_policy(api_name, geocatalog_url, managed_identity_client_id)
        
        if use_products and config_file:
            # Load product configurations from file
            with open(config_file, 'r') as f:
                product_configs = json.load(f)
            setup.create_products_and_subscriptions(api_name, product_configs)
        elif use_products:
            # Create default product configurations
            product_configs = [
                {
                    "name": "basic",
                    "display_name": "Basic Tier",
                    "allowed_collections": "sentinel-2-l2a"
                },
                {
                    "name": "premium", 
                    "display_name": "Premium Tier",
                    "allowed_collections": "sentinel-2-l2a,landsat-8-c2-l2,sentinel-1-grd"
                }
            ]
            setup.create_products_and_subscriptions(api_name, product_configs)
        else:
            # Create simple named value for allowed collections
            setup.create_named_value("allowed-collections", allowed_collections)
            
        # Create operation policies
        setup.create_operation_policies(api_name, allowed_collections)
        
        logger.info("✅ GeoCatalog APIM setup completed successfully!")
        logger.info(f"Your API is available at: https://{apim_service_name}.azure-api.net")
        
    except Exception as e:
        logger.error(f"❌ Setup failed: {e}")
        raise

if __name__ == '__main__':
    main()