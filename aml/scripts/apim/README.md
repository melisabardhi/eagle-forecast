# GeoCatalog APIM Proxy Setup

This directory contains scripts to automatically set up Azure API Management (APIM) as a proxy for GeoCatalog services. The solution implements authentication via user-assigned managed identity and collection-level RBAC (Role-Based Access Control) as described in the [GeoCatalog + APIM guide](https://gist.github.com/ghidalgo3/ce6cac6a1cd3a324e77b064e48da05ca).

## What This Sets Up

The script creates a complete APIM configuration that:

1. **Proxies GeoCatalog requests** through APIM with managed identity authentication
2. **Implements collection-level RBAC** to restrict access to specific collections  
3. **Blocks discovery endpoints** (root `/`, `/stac/collections`) to prevent collection enumeration
4. **Validates search requests** to ensure only allowed collections are accessed
5. **Protects SAS token generation** to authorized collections only
6. **Supports subscription tiers** for different levels of access (Basic, Premium, Enterprise)

## Prerequisites

Before running the setup script, ensure you have:

1. **Azure CLI** installed and logged in with appropriate permissions
2. **GeoCatalog instance** deployed and accessible
3. **User-assigned managed identity** with `GeoCatalog Reader` role on your GeoCatalog
4. **APIM instance** created (or permissions to create one)
5. **Python 3.8+** with pip

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Ensure Azure CLI is logged in:
```bash
az login
az account set --subscription "your-subscription-id"
```

## Basic Usage

### Simple Setup (Single Collection Access)

For a basic setup where all users get access to the same collections:

```bash
python setup_geocatalog_apim.py \
    --subscription-id "12345678-1234-1234-1234-123456789012" \
    --resource-group "my-resource-group" \
    --apim-service-name "my-apim-service" \
    --geocatalog-url "https://mygeocatalog.abc123.westus2.geocatalog.spatio.azure.com" \
    --managed-identity-client-id "87654321-4321-4321-4321-210987654321" \
    --allowed-collections "sentinel-2-l2a,landsat-8-c2-l2"
```

### Advanced Setup (Subscription Tiers)

For subscription-based access with different collection tiers:

```bash
python setup_geocatalog_apim.py \
    --subscription-id "12345678-1234-1234-1234-123456789012" \
    --resource-group "my-resource-group" \
    --apim-service-name "my-apim-service" \
    --geocatalog-url "https://mygeocatalog.abc123.westus2.geocatalog.spatio.azure.com" \
    --managed-identity-client-id "87654321-4321-4321-4321-210987654321" \
    --use-products \
    --config-file product_config.json
```

## Configuration Files

### product_config.json

Defines subscription tiers with different collection access levels:

```json
[
    {
        "name": "basic",
        "display_name": "Basic Tier",
        "allowed_collections": "sentinel-2-l2a",
        "description": "Basic access to Sentinel-2 L2A data only"
    },
    {
        "name": "premium", 
        "display_name": "Premium Tier",
        "allowed_collections": "sentinel-2-l2a,landsat-8-c2-l2,sentinel-1-grd",
        "description": "Premium access to multiple satellite collections"
    }
]
```

## How It Works

### Authentication Flow

1. Requests to APIM are received at `https://your-apim.azure-api.net`
2. APIM uses the managed identity to get a token for GeoCatalog API (`https://geocatalog.spatio.azure.com`)
3. The token is attached to requests forwarded to your GeoCatalog backend
4. Responses are returned with URLs rewritten to point back to APIM

### Collection-Level RBAC

The setup creates policies that:

- **Block discovery**: Prevent enumeration of all collections via `/` and `/stac/collections`
- **Validate search**: Check `collections` parameter in GET/POST `/stac/search` requests
- **Protect SAS tokens**: Only allow SAS token generation for authorized collections
- **Guard data access**: Validate collection access for `/data/mosaic/` endpoints

### Subscription Tiers (Optional)

When using products and subscriptions:

- Each product defines allowed collections via named values
- Subscription keys determine which product (and collection set) applies
- Users include subscription keys in request headers: `Ocp-Apim-Subscription-Key: your-key`

## Example API Calls

After setup, clients can call your APIM gateway:

### STAC Search (GET)
```bash
curl "https://your-apim.azure-api.net/stac/search?collections=sentinel-2-l2a&bbox=-122.5,37.5,-122.0,38.0&limit=5"
```

### STAC Search (POST)  
```bash
curl -X POST "https://your-apim.azure-api.net/stac/search" \
  -H "Content-Type: application/json" \
  -d '{
    "collections": ["sentinel-2-l2a"],
    "bbox": [-122.5, 37.5, -122.0, 38.0],
    "datetime": "2024-01-01T00:00:00Z/2024-02-01T00:00:00Z",
    "limit": 5
  }'
```

### With Subscription Key
```bash
curl -H "Ocp-Apim-Subscription-Key: your-subscription-key" \
  "https://your-apim.azure-api.net/stac/search?collections=sentinel-2-l2a"
```

### SAS Token Generation
```bash
curl "https://your-apim.azure-api.net/sas/token/sentinel-2-l2a"
```

## APIM Operations Created

The script creates these operations with appropriate policies:

| Operation | Method | Path | Purpose |
|-----------|--------|------|---------|
| GET Wildcard | GET | `/*` | Proxy all unmatched GET requests |
| POST Wildcard | POST | `/*` | Proxy all unmatched POST requests |
| Get Single Collection | GET | `/stac/collections/{collection_id}` | Collection access with RBAC |
| Get Collection Items | GET | `/stac/collections/{collection_id}/items` | Items access with RBAC |
| GET Search | GET | `/stac/search` | Search with collection validation |
| POST Search | POST | `/stac/search` | Search with collection validation |
| Block Root | GET | `/` | Return 404 to prevent discovery |
| Block Collections | GET | `/stac/collections` | Return 404 to prevent discovery |
| GET SAS Token | GET | `/sas/token/{collection_id}` | SAS tokens with RBAC |
| Data Mosaic | GET/POST | `/data/mosaic/collections/{collectionId}/*` | Tile/crop access with RBAC |

## Policy Details

### API-Level Policy
- Authenticates using managed identity
- Rewrites response URLs from GeoCatalog backend to APIM gateway

### Operation-Level Policies  
- **Block policies**: Return 404 for discovery endpoints
- **Collection validation**: Check path parameters against allowed collections
- **Search validation**: Validate `collections` in query params or JSON body
- **Forbidden response**: Return 403 when unauthorized collections are requested

### Product-Level Policies (when using subscriptions)
- Set `allowedCsv` variable based on subscription tier
- Enable different collection access per product

## Troubleshooting

### Common Issues

1. **Authentication failures**
   - Verify managed identity has `GeoCatalog Reader` role on the GeoCatalog
   - Ensure client ID is correct

2. **403 Forbidden responses**  
   - Check that requested collections are in the allowed list
   - Verify named values are set correctly in APIM

3. **404 Not Found**
   - Confirm GeoCatalog URL is correct and accessible
   - Check that operations are created properly

### Checking Configuration

After running the script, verify the setup in the Azure portal:

1. Navigate to your APIM instance
2. Check **APIs** → **GeoCatalog API** → **Operations** 
3. Review **Named values** for allowed collections
4. Examine **Products** if using subscription tiers
5. Test policies using the **Test** tab

## Script Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `--subscription-id` | Yes | Azure subscription ID |
| `--resource-group` | Yes | Resource group containing APIM |
| `--apim-service-name` | Yes | Name of APIM service |
| `--api-name` | No | API name to create (default: geocatalog-api) |
| `--geocatalog-url` | Yes | Full URL to GeoCatalog backend |
| `--managed-identity-client-id` | Yes | Client ID of managed identity |
| `--allowed-collections` | No | Comma-separated collections (default: sentinel-2-l2a) |
| `--use-products` | No | Enable subscription-based tiers |
| `--config-file` | No | JSON file with product configurations |

## Security Considerations

- The managed identity should have **minimal permissions** (only GeoCatalog Reader)
- Collection allow-lists prevent unauthorized data access
- APIM policies block discovery to prevent collection enumeration  
- SAS token generation is restricted to authorized collections
- Subscription keys can be rotated as needed

## Next Steps

After running the setup:

1. **Create subscriptions** for your users (if using products)
2. **Test the API** with sample requests
3. **Monitor usage** via APIM analytics
4. **Update collection lists** by modifying named values
5. **Add rate limiting** policies if needed
6. **Set up alerts** for authentication failures or policy violations

## Support

For issues specific to:
- **APIM configuration**: Check Azure APIM documentation
- **GeoCatalog**: Refer to GeoCatalog documentation  
- **This script**: Review the source code and error messages

The script includes comprehensive logging to help diagnose setup issues.