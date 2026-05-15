#!/bin/bash

# Endpoint creation script, for use prior to deploying model with Foundry
# ----------------------------------------
# Config
# ----------------------------------------
RESOURCE_GROUP=""
WORKSPACE_NAME=""
ENDPOINT_NAME=""

STORAGE_ACCOUNT_NAME=""
CONTAINER_NAME=""

SUBSCRIPTION_ID=$(az account show --query id -o tsv)

echo "Using subscription: $SUBSCRIPTION_ID"

# ----------------------------------------
# Discover the Workspace ACR
# ----------------------------------------
echo "Discovering ACR used by workspace..."

ACR_ID=$(az ml workspace show \
  --name "$WORKSPACE_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query container_registry -o tsv)

if [[ -z "$ACR_ID" ]]; then
  echo "ERROR: Workspace does not have an attached ACR."
  exit 1
fi

ACR_NAME=$(basename "$ACR_ID")

echo "Workspace ACR: $ACR_NAME"
echo "ACR Resource ID: $ACR_ID"

# ----------------------------------------
# Create User‑Assigned Managed Identity
# ----------------------------------------
echo "Creating managed identity: $ENDPOINT_NAME"

az identity create \
  --name "$ENDPOINT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  >/dev/null

CLIENT_ID=$(az identity show \
  --name "$ENDPOINT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query clientId -o tsv)

UAI_ID="/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/${ENDPOINT_NAME}"

echo "Managed Identity Client ID: $CLIENT_ID"

# ----------------------------------------
# Assign RBAC Roles
# ----------------------------------------

# Storage Blob Data Contributor
echo "Assigning Storage Blob Data Contributor..."
az role assignment create \
  --assignee "$CLIENT_ID" \
  --role "Storage Blob Data Contributor" \
  --scope "/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.Storage/storageAccounts/${STORAGE_ACCOUNT_NAME}" \
  >/dev/null

# ACR Pull
echo "Assigning AcrPull on workspace ACR..."
az role assignment create \
  --assignee "$CLIENT_ID" \
  --role "AcrPull" \
  --scope "$ACR_ID" \
  >/dev/null

echo "RBAC assignments complete."

# ----------------------------------------
# Create the Online Endpoint
# ----------------------------------------
echo "Creating online endpoint with user-assigned identity..."

az ml online-endpoint create \
  --name "$ENDPOINT_NAME" \
  --workspace "$WORKSPACE_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  -f endpoint.yml \
  --set identity.type="user_assigned" \
  --set identity.user_assigned_identities[0].resource_id="$UAI_ID"

echo "Endpoint created successfully."
