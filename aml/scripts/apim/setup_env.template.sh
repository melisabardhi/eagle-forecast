#!/bin/bash
# Environment configuration for GeoCatalog APIM setup
# Copy this file to setup_env.sh and customize with your values

# Azure Configuration
export AZURE_SUBSCRIPTION_ID="your-subscription-id-here"
export AZURE_RESOURCE_GROUP="your-resource-group-name"
export APIM_SERVICE_NAME="your-apim-service-name"

# GeoCatalog Configuration  
export GEOCATALOG_URL="https://your-name.your-id.your-region.geocatalog.spatio.azure.com"
export MANAGED_IDENTITY_CLIENT_ID="your-managed-identity-client-id"

# API Configuration
export API_NAME="geocatalog-api"  # Optional, will use default if not set
export ALLOWED_COLLECTIONS="sentinel-2-l2a,landsat-8-c2-l2"  # Comma-separated list

# Product/Subscription Configuration (optional)
export USE_PRODUCTS="false"  # Set to "true" to enable subscription tiers
export PRODUCT_CONFIG_FILE="product_config.json"

# Validation Configuration
export APIM_GATEWAY_URL="https://${APIM_SERVICE_NAME}.azure-api.net"

echo "Environment variables loaded for GeoCatalog APIM setup"
echo "Gateway URL will be: ${APIM_GATEWAY_URL}"

# Function to run the setup with loaded environment variables
run_setup() {
    echo "Running GeoCatalog APIM setup..."
    
    local setup_args=(
        --subscription-id "$AZURE_SUBSCRIPTION_ID"
        --resource-group "$AZURE_RESOURCE_GROUP" 
        --apim-service-name "$APIM_SERVICE_NAME"
        --geocatalog-url "$GEOCATALOG_URL"
        --managed-identity-client-id "$MANAGED_IDENTITY_CLIENT_ID"
        --allowed-collections "$ALLOWED_COLLECTIONS"
    )
    
    if [[ "$API_NAME" != "geocatalog-api" && -n "$API_NAME" ]]; then
        setup_args+=(--api-name "$API_NAME")
    fi
    
    if [[ "$USE_PRODUCTS" == "true" ]]; then
        setup_args+=(--use-products)
        if [[ -f "$PRODUCT_CONFIG_FILE" ]]; then
            setup_args+=(--config-file "$PRODUCT_CONFIG_FILE")
        fi
    fi
    
    python setup_geocatalog_apim.py "${setup_args[@]}"
}

# Function to run validation with loaded environment variables
run_validation() {
    echo "Running GeoCatalog APIM validation..."
    
    local validate_args=(
        --gateway-url "$APIM_GATEWAY_URL"
        --allowed-collections "$ALLOWED_COLLECTIONS"
    )
    
    if [[ -n "$SUBSCRIPTION_KEY" ]]; then
        validate_args+=(--subscription-key "$SUBSCRIPTION_KEY")
    fi
    
    python validate_apim_setup.py "${validate_args[@]}"
}

# Usage examples
echo ""
echo "Usage examples:"  
echo "  source setup_env.sh           # Load environment variables"
echo "  run_setup                     # Run the setup script with loaded env vars"
echo "  run_validation                # Run validation with loaded env vars"
echo ""
echo "Or run manually:"
echo "  python setup_geocatalog_apim.py --subscription-id \$AZURE_SUBSCRIPTION_ID ..."
echo "  python validate_apim_setup.py --gateway-url \$APIM_GATEWAY_URL ..."