# Nested-EAGLE BYOC Inference Container

This directory contains the Bring Your Own Container (BYOC) package for deploying Nested-EAGLE as an Azure ML managed online endpoint. It allows users to deploy the model to their own Azure subscription and call it with initial conditions to get back a forecast.

## What's in this folder

```
byoc/
├── Dockerfile     # Container image — CUDA 12.1 base + anemoi-inference + eagle-tools
├── conda.yaml     # Python dependencies
├── score.py       # AML managed online endpoint scoring script (init + run)
└── README.md      # This file
```

The scoring script (`score.py`) copies two helpers from `poc/`:
- `postproc.py` — splits raw forecast into global.nc (GFS 0.25°) + conus.nc (HRRR 6km)
- `utils.py` — shared utilities

## Prerequisites

- Azure subscription with:
  - Azure Container Registry (ACR) to push the image
  - Azure ML workspace
  - GPU quota: `Standard_NC40ads_H100_v5` (H100 80GB) — at least 1 instance
- Model checkpoint registered in AML model registry (see `aml/provision.py`)
- Static grid file `hrrr_06km.nc` registered alongside the checkpoint

## Step 1: Build and push the container image

```bash
# From the repo root
cd byoc

# Copy inference helpers from poc/
cp ../poc/postproc.py .
cp ../poc/utils.py .

# Build
ACR_NAME="<your-acr-name>"
docker build -t ${ACR_NAME}.azurecr.io/nested-eagle-byoc:latest .

# Push
az acr login --name ${ACR_NAME}
docker push ${ACR_NAME}.azurecr.io/nested-eagle-byoc:latest
```

## Step 2: Register the container as an AML environment

```python
from azure.ai.ml.entities import Environment, BuildContext

env = Environment(
    name="nested-eagle-byoc",
    image=f"{ACR_NAME}.azurecr.io/nested-eagle-byoc:latest",
    description="Nested-EAGLE BYOC inference container for AML managed online endpoint",
)
ml_client.environments.create_or_update(env)
```

## Step 3: Deploy as a managed online endpoint

```python
from azure.ai.ml.entities import (
    ManagedOnlineEndpoint,
    ManagedOnlineDeployment,
    Model,
    CodeConfiguration,
)

# Create endpoint
endpoint = ManagedOnlineEndpoint(
    name="nested-eagle",
    description="Nested-EAGLE NRT inference endpoint",
    auth_mode="key",
)
ml_client.online_endpoints.begin_create_or_update(endpoint).result()

# Deploy
deployment = ManagedOnlineDeployment(
    name="default",
    endpoint_name="nested-eagle",
    model=f"azureml:nested-eagle:1",          # registered checkpoint
    environment=f"azureml:nested-eagle-byoc:1",
    code_configuration=CodeConfiguration(
        code="./byoc",
        scoring_script="score.py",
    ),
    instance_type="Standard_NC40ads_H100_v5",  # H100 80GB required
    instance_count=1,
    environment_variables={
        "CHECKPOINT_PATH": "/mnt/models/inference-last.ckpt",
        "GRID_FILE":       "/mnt/models/hrrr_06km.nc",
    },
)
ml_client.online_deployments.begin_create_or_update(deployment).result()

# Set 100% traffic to default deployment
endpoint.traffic = {"default": 100}
ml_client.online_endpoints.begin_create_or_update(endpoint).result()
```

## Step 4: Call the endpoint

The endpoint expects the user to supply **pre-processed initial conditions** (GFS and HRRR already downloaded and converted to Zarr). It does not perform preprocessing.

```python
import json
from azure.ai.ml import MLClient
from azure.identity import DefaultAzureCredential

ml_client = MLClient(DefaultAzureCredential(), subscription_id, resource_group, workspace_name)

request = {
    "gfs_zarr_path":  "az://my-storage/initial_conditions/2026/04/20/00/gfs.zarr",
    "hrrr_zarr_path": "az://my-storage/initial_conditions/2026/04/20/00/hrrr.zarr",
    "ic_timestamp":   "2026-04-20T00",
    "lead_time":      240
}

response = ml_client.online_endpoints.invoke(
    endpoint_name="nested-eagle",
    request_file=json.dumps(request),
)
print(response)
# {"status": "success", "forecast_nc": "/tmp/...", "global_nc": "/tmp/...", "conus_nc": "/tmp/..."}
```

## Notes

- **Preprocessing not included.** Users must supply GFS and HRRR Zarr initial conditions. See `poc/preproc.py` for the preprocessing pipeline.
- **Output files** are written to `/tmp/nested-eagle-output/` inside the container. For persistent storage, mount an Azure Blob datastore or retrieve via the response paths.
- **Cost:** The H100 instance runs continuously while the endpoint is active (~$6.98/hr). Consider scaling to zero or using batch endpoints for infrequent use.
- **BYOC vs. NRT pipeline:** This container is for on-demand user inference. NOAA's NRT operational pipeline (running every 6 hours) uses the AML scheduled pipeline in `aml/` and is separate.
