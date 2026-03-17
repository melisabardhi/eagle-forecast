# Nested-EAGLE: Azure ML Deployment Guide

Deploy the Nested-EAGLE NRT weather forecast pipeline on Azure Machine Learning as a scheduled job running every 6 hours.

## Architecture

```
Every 6 hours (00Z, 06Z, 12Z, 18Z)
│
├── Step 1: CPU Command Job (preprocessing)
│   ├── Calculate NRT timestamp (floor to 6h - 6h latency)
│   ├── Download GFS initial conditions → Zarr
│   └── Download HRRR initial conditions → regrid to 6km → Zarr
│
└── Step 2: GPU Command Job (inference + upload)
    ├── Load checkpoint from AML Model Registry
    ├── Load initial conditions (GFS global + HRRR cutout)
    ├── Run 40 autoregressive steps → 240h forecast
    ├── Write NetCDF output
    └── Upload to output blob container (customer-owned, MPC Pro gets read access)
```

## Prerequisites

- Azure subscription with an AML workspace
- GPU quota: H100 80GB (`Standard_NC40ads_H100_v5`) or A100 80GB (`Standard_NC24ads_A100_v4`)
- Azure CLI with ML extension (`az extension add -n ml`)
- Python 3.12+ with `azure-ai-ml` and `azure-identity` packages
- Model checkpoint (`inference-last.ckpt`)

## Step 0: Local Setup (VS Code)

### Install VS Code Extensions
- **Python** (Microsoft)
- **Azure Machine Learning** (Microsoft)
- **Azure Account** (Microsoft)

### Install Azure CLI + ML Extension
```bash
# Install Azure CLI: https://learn.microsoft.com/en-us/cli/azure/install-azure-cli
az extension add -n ml
```

### Sign In
```bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"
```

### Create Python Environment
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Mac/Linux: source .venv/bin/activate
pip install azure-ai-ml azure-identity azure-storage-blob
```

### Verify Connection
Edit `aml/config.py` with your workspace details and run:
```bash
python aml/setup_client.py
```

## Step 1: Verify GPU Quota

```bash
az ml compute list-usage \
  --workspace-name <WORKSPACE> \
  --resource-group <RESOURCE_GROUP> \
  -o table
```

Check quota for both GPU families (customer has access to both):
- `NC40adsH100v5` — at least 40 cores for H100 80GB
- `NC24adsA100v4` — at least 24 cores for A100 80GB (cost-optimization option)

If quota needs increase, request via Azure Portal → Subscriptions → Usage + quotas (takes 1-5 business days).

> **Portal alternative:** Azure Portal → Subscriptions → Usage + quotas. The portal view is easier to browse across VM families and request increases.

## Step 2: Create Output Blob Container

Create a storage account and container for forecast outputs. The AML pipeline writes here; the MPC Pro team will be granted read access to ingest data into Planetary Computer.

```bash
# Create storage account (or use an existing one in the same region as the AML workspace)
az storage account create \
  --name <FORECAST_STORAGE_ACCOUNT> \
  --resource-group <RESOURCE_GROUP> \
  --location <REGION> \
  --sku Standard_LRS

# Create container for forecast outputs
az storage container create \
  --account-name <FORECAST_STORAGE_ACCOUNT> \
  --name nested-eagle-forecasts

# Grant AML workspace managed identity write access
az role assignment create \
  --assignee <WORKSPACE_MANAGED_IDENTITY_OBJECT_ID> \
  --role "Storage Blob Data Contributor" \
  --scope /subscriptions/<SUB>/resourceGroups/<RG>/providers/Microsoft.Storage/storageAccounts/<FORECAST_STORAGE_ACCOUNT>
```

To find the workspace managed identity object ID:
```bash
az ml workspace show \
  --name <WORKSPACE> \
  --resource-group <RESOURCE_GROUP> \
  --query identity.principal_id -o tsv
```

Later, grant the MPC Pro team read access:
```bash
az role assignment create \
  --assignee <MPC_PRO_TEAM_PRINCIPAL_ID> \
  --role "Storage Blob Data Reader" \
  --scope /subscriptions/<SUB>/resourceGroups/<RG>/providers/Microsoft.Storage/storageAccounts/<FORECAST_STORAGE_ACCOUNT>
```

## Step 3: Generate Static Grid File (One-Time)

```bash
python poc/config/hrrr_6km.py
```

Upload `hrrr_06km.nc` to the checkpoint datastore using the Azure Portal OR the Azure CLI. 

```bash
az storage blob upload \
  --account-name <storage-account-name> \
  --container-name <container-name> \
  --name hrrr_06km.nc \
  --file ./hrrr_06km.nc
```

## Step 4: Register Checkpoint

Create a datastore pointing to the checkpoint storage, then register the model:

```python
from azure.ai.ml.entities import Model

# Path to model assets that will be registered with the model
MODEL_PATH="azureml://datastores/<CHECKPOINT_DATASTORE>/paths/poc/inference-last.ckpt"

model = Model(
    name="nested-eagle",
    version="1",
    path=MODEL_PATH, 
    type="custom_model",
    description="Nested-EAGLE NRT weather forecast model",
    tags={"framework": "anemoi-inference", "grid": "nested-cutout-6km", "lead_time": "240h"},
)
ml_client.models.create_or_update(model)
```

> **Portal alternative:** AML Studio → Models → Register → From datastore. Select the checkpoint datastore and browse to the `.ckpt` file.

## Step 5: Provision Compute Clusters

```python
from azure.ai.ml.entities import AmlCompute

# CPU cluster for preprocessing (scale-to-zero)
cpu_cluster = AmlCompute(
    name="eagle-cpu",
    size="Standard_D16s_v5",
    min_instances=0,
    max_instances=1,
    idle_time_before_scale_down=300,
)
ml_client.compute.begin_create_or_update(cpu_cluster)

# GPU cluster for inference (scale-to-zero)
gpu_cluster = AmlCompute(
    name="eagle-gpu",
    size="Standard_NC40ads_H100_v5",
    min_instances=0,
    max_instances=1,
    idle_time_before_scale_down=300,
)
ml_client.compute.begin_create_or_update(gpu_cluster)
```

> **Portal alternative:** AML Studio → Compute → New → Compute cluster. Set VM size, min nodes = 0, max nodes = 1, and idle scale-down = 300s. Create one cluster for each (CPU and GPU).

## Step 6: Register Environment

The environment is defined in `aml/environment/` (Dockerfile + conda.yaml):

```python
from azure.ai.ml.entities import Environment

env = Environment(
    name="eagle-nrt",
    build={"path": "aml/environment/"},
)
ml_client.environments.create_or_update(env)
```

> **Portal alternative:** AML Studio → Environments → Custom environments → Create. Upload the `aml/environment/` folder (Dockerfile + conda.yaml) as the build context.

## Step 7: Test Preprocessing (CPU)

```python
from azure.ai.ml import command

preproc_job = command(
    code="./poc",
    command="python preproc.py --config nested_eagle.yaml",
    environment="eagle-nrt:1",
    compute="eagle-cpu",
    display_name="eagle-preproc-test",
    experiment_name="nested-eagle-nrt",
)
ml_client.jobs.create_or_update(preproc_job)
```

## Step 8: Test Inference (GPU)

```python
inference_job = command(
    code="./poc",
    command="python inference.py",
    environment="eagle-nrt:1",
    compute="eagle-gpu",
    display_name="eagle-inference-test",
    experiment_name="nested-eagle-nrt",
)
ml_client.jobs.create_or_update(inference_job)
```

Monitor peak VRAM usage during the run. If < 20GB, consider switching to A10 24GB for cost savings.

## Step 9: Build 2-Step Pipeline

Build 2 step pipeline. Specify the registered model created in the previous steps. 

```bash
python pipeline.py --checkpoint_path "azureml://models/nested-eagle-model/versions/1"
```

## Step 10: Enable 6h Schedule

```python
from azure.ai.ml.entities import RecurrenceTrigger, JobSchedule

schedule = JobSchedule(
    name="nested-eagle-6h",
    trigger=RecurrenceTrigger(
        frequency="hour",
        interval=6,
        start_time="2026-04-01T00:00:00Z",
        time_zone="UTC",
    ),
    create_job=nested_eagle_pipeline,
)
ml_client.schedules.begin_create_or_update(schedule)
```

## MPC Pro Integration

Once the pipeline is running and writing NetCDF to the output container:

1. Share the storage account name and container with the MPC Pro team
2. Grant them `Storage Blob Data Reader` on the container (see Step 2)
3. Provide blob path convention: `nested-eagle/v1/{YYYY}/{MM}/{DD}/{HH}/forecast.nc`
4. MPC Pro team generates virtual Zarr references and creates STAC catalog entry
5. Forecasts become publicly accessible via Planetary Computer API

## Files

```
aml/
├── README.md              # This file — deployment guide
├── config.py              # Shared configuration (workspace, storage, cluster names)
├── setup_client.py        # Step 0: verify AML SDK connection
├── provision.py           # Steps 3+5+6: register model, create clusters, register env
├── test_preproc.py        # Step 7: submit CPU preprocessing test job
├── test_inference.py      # Step 8: submit GPU inference test job
├── pipeline.py            # Steps 9+10: build pipeline + create 6h schedule
└── environment/
    ├── conda.yaml         # Python dependencies
    └── Dockerfile         # CUDA base image + conda env
```

## Quick Start

After completing Steps 0-2 (local setup, quota check, output container):

```bash
# 1. Edit aml/config.py with your workspace and storage details

# 2. Verify connection
python aml/setup_client.py

# 3. Provision all resources (model, compute, environment)
python aml/provision.py

# 4. Generate static grid file (one-time)
python poc/config/hrrr_6km.py

# 5. Test preprocessing
python aml/test_preproc.py

# 6. Test inference (after preproc completes)
python aml/test_inference.py

# 7. Run full pipeline test
python aml/pipeline.py

# 8. Enable 6h schedule (after pipeline test succeeds)
python aml/pipeline.py --schedule
```
