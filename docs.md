# Nested-EAGLE: AML Deployment & MPC Pro Integration

## Table of Contents
- [Overview](#overview)
- [Architecture](#architecture)
- [Azure ML Compute Sizing (NC-Series)](#azure-ml-compute-sizing-nc-series)
- [Estimated Run Times](#estimated-run-times)
- [Checkpoint Storage](#checkpoint-storage)
- [Input Data (Initial Conditions)](#input-data-initial-conditions)
- [Output to Microsoft Planetary Computer (MPC Pro)](#output-to-microsoft-planetary-computer-mpc-pro)
- [AML Endpoint Deployment](#aml-endpoint-deployment)
- [Pipeline Flow](#pipeline-flow)
- [Open Questions / Next Steps](#open-questions--next-steps)
- [Deployment Plan](#deployment-plan)
- [Milestone Plan](#milestone-plan)
- [Virtual Zarr: Code Changes Required](#virtual-zarr-code-changes-required)
- [Cost Optimization Plan](#cost-optimization-plan)
- [Dependency Graph](#dependency-graph)

---

## Overview

Nested-EAGLE is an AI weather forecasting model built on the ECMWF Anemoi framework. It operates in near-real-time (NRT) by:

1. Computing an NRT timestamp (floor to 6h intervals, minus 6h latency)
2. Downloading GFS (global) and HRRR (CONUS, regridded to 6km) initial conditions
3. Running GPU inference with a nested cutout approach (HRRR nested inside GFS)
4. Producing a 240-hour (10-day) forecast

The pipeline is designed to run every **6 hours**, aligned with GFS/HRRR initialization times (00Z, 06Z, 12Z, 18Z).

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     AML Workspace (Eagle)                       │
│                                                                 │
│  ┌──────────────┐    ┌──────────────────┐    ┌───────────────┐  │
│  │  Preproc      │    │  Inference        │    │  Output        │  │
│  │  (CPU node)   │───▶│  (GPU node)       │───▶│  (CPU node)    │  │
│  │              │    │                  │    │               │  │
│  │ - NRT timestamp│    │ - Load checkpoint │    │ - NetCDF write │  │
│  │ - Download GFS │    │ - eagle_inference │    │ - Upload to    │  │
│  │ - Download HRRR│    │ - 240h forecast   │    │   MPC Pro blob │  │
│  │ - Regrid HRRR  │    │                  │    │               │  │
│  └──────────────┘    └──────────────────┘    └───────────────┘  │
│         │                     │                      │          │
│         ▼                     ▼                      ▼          │
│  ┌──────────────┐    ┌──────────────────┐    ┌───────────────┐  │
│  │ Planetary     │    │ Azure Blob        │    │ MPC Pro        │  │
│  │ Computer      │    │ eagle-checkpoints │    │ (NetCDF output)│  │
│  │ (GFS + HRRR)  │    │ (public access)   │    │               │  │
│  └──────────────┘    └──────────────────┘    └───────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Azure ML Compute Sizing (NC-Series)

### Model Characteristics
| Property | Value |
|---|---|
| Framework | Anemoi (PyTorch) + flash-attention |
| Checkpoint size | >1 GB (`inference-last.ckpt`) |
| Grid | Nested cutout: HRRR 6km (CONUS) inside GFS (global) |
| Variables | 14 atmospheric variables × 12 pressure levels + surface |
| Lead time | 240 hours (40 steps at 6h intervals) |
| Attention | Flash Attention (requires Ampere+ GPU architecture) |

### GPU Requirements

**Flash Attention requires Ampere (A100) or newer GPU architecture.** H100 (Hopper) is confirmed and provisioned as `eagle-gpu-h100`.

#### Confirmed: Standard_NC40ads_H100_v5
| Spec | Value |
|---|---|
| GPU | 1× NVIDIA H100 80GB NVL |
| vCPUs | 40 |
| RAM | 320 GB |
| Temp Storage | 1800 GB SSD |
| GPU Memory | 80 GB |
| Estimated cost | ~$6.98/hr (pay-as-you-go, East US) |

**Why this SKU:**
- Customer has H100 quota available — no quota request delay
- H100 80GB (Hopper architecture) provides ample VRAM for nested cutout grid
- Flash-attn is fully compatible with Hopper (faster than Ampere)
- 320 GB system RAM handles large initial condition Zarr datasets with headroom
- Faster inference than A100 — inference completes in ~10 min
- **Confirmed as production GPU** — A100 not available in workspace

#### Not Recommended
| SKU | Reason |
|---|---|
| NC6s_v3 / NC12s_v3 / NC24s_v3 | V100 GPU — flash-attn requires Ampere+ |
| NC4as_T4_v3 / NC8as_T4_v3 | T4 (Turing) — flash-attn requires Ampere+ |
| NCA10v4 series | A10 24GB — possible cost-optimization target, needs VRAM validation |

### Preprocessing Compute (CPU-only)

The preprocessing step (download + regrid) is CPU-bound and I/O-heavy. Options:

| SKU | vCPUs | RAM | Use Case |
|---|---|---|---|
| Standard_D16s_v5 | 16 | 64 GB | Sufficient for GFS + HRRR download + regrid |
| Standard_D32s_v5 | 32 | 128 GB | Faster if parallel downloads needed |

---

## Estimated Run Times

> **Note:** These are estimates based on comparable Anemoi-based weather models. Actual times should be validated during testing with the real checkpoint.

### On Standard_NC40ads_H100_v5

| Stage | Estimated Time | Compute |
|---|---|---|
| Preprocessing (GFS download + format) | 5–15 min | CPU |
| Preprocessing (HRRR download + regrid to 6km) | 10–25 min | CPU |
| Checkpoint loading | 1–3 min | GPU |
| Inference (240h / 40 autoregressive steps) | 5–20 min | GPU |
| Output write (NetCDF) + upload to MPC Pro | 5–10 min | CPU |
| **Total end-to-end** | **~30–70 min** | |

### Cost Per Run (Estimated)
| Scenario | Time | Cost |
|---|---|---|
| H100 (optimistic) | ~25 min | ~$2.91 |
| H100 (conservative) | ~60 min | ~$6.98 |
| Per day (4 runs × 6h cycle) | ~1.7–4 hrs | ~$12–28/day |
| Per month (continuous NRT) | ~50–120 hrs | ~$350–840/mo |

*Cost-optimization: if peak VRAM < 20GB, switch to A10 24GB (~$1.10/hr) for ~$66/month.*

---

## Checkpoint Storage

Checkpoints are stored in a **public Azure Blob Storage account**:

```
Account name:  eaglecheckpoints
Container:     eagle-checkpoints
Path:          poc/
```

Verify access:
```bash
az storage blob list \
  --account-name eaglecheckpoints \
  --container-name eagle-checkpoints \
  --output table
```

In the AML deployment, the checkpoint should be:
1. **Registered as an AML Model** (preferred) — enables versioning and lineage tracking
2. Or mounted from blob storage at runtime via AML datastore

The `nested_eagle.yaml` config needs `checkpoint_path` updated to point to the AML-accessible location (e.g., `/mnt/models/eagle-checkpoint/poc/`).

---

## Input Data (Initial Conditions)

### Sources (Already Available on Planetary Computer via NODD)

| Dataset | Planetary Computer Link | Resolution | Update Freq |
|---|---|---|---|
| GFS | [GFS Data Catalog](https://planetarycomputer.microsoft.com/dataset/noaa-gfs) | 0.25° global | 6h |
| HRRR | [HRRR Data Catalog](https://planetarycomputer.microsoft.com/dataset/noaa-hrrr) | 3km CONUS | 1h |

### How the POC Fetches Data
- **GFS**: via `ufs2arco` `gfs_archive` source → downloads GRIB, converts to Zarr
- **HRRR**: via `ufs2arco` `aws_hrrr_archive` source → downloads GRIB, regrids to 6km, converts to Zarr

### Azure Consideration
The POC currently pulls HRRR from AWS S3 (`aws_hrrr_archive`). For AML deployment:
- **Option A (Recommended):** Use Planetary Computer HRRR/GFS data directly since it's already available via NODD. This avoids cross-cloud data transfer costs.
- **Option B:** Keep `ufs2arco` sources as-is (still pulls from AWS/NOAA). Works but incurs egress.

### Static File: HRRR 6km Grid
The HRRR regrid requires a one-time generated `hrrr_06km.nc` file (see `config/hrrr_6km.py`). This should be:
1. Generated once during environment setup
2. Stored alongside the checkpoint in blob storage or as a registered AML dataset

---

## Output to Microsoft Planetary Computer (MPC Pro)

### What MPC Pro Needs

MPC Pro will serve as the public distribution endpoint for Nested-EAGLE forecast outputs. Here's what's required:

#### 1. Output Format: NetCDF
- MPC Pro **supports NetCDF natively** — no need to convert to Zarr initially
- The model's inference output from `eagle.tools.inference` writes forecasts that can be saved as NetCDF
- Follow CF Conventions for metadata (standard_name, units, coordinates)

#### 2. Azure Blob Storage (Landing Zone)
MPC Pro ingests data from a designated Azure Blob Storage container. Required setup:

```
Storage Account:   <to-be-provisioned by MPC Pro team>
Container:         nested-eagle-forecasts  (example)
Path convention:   nested-eagle/v1/{YYYY}/{MM}/{DD}/{HH}/forecast.nc
```

The AML pipeline's final step must upload output NetCDF files to this blob container.

#### 3. STAC Metadata Catalog
MPC Pro uses SpatioTemporal Asset Catalogs (STAC) to index and discover data. Requirements:

| STAC Field | Value |
|---|---|
| Collection ID | `noaa-nested-eagle` |
| Item ID | `nested-eagle-{YYYYMMDD}-{HH}z` |
| Geometry | Global (GFS) + CONUS bbox (HRRR cutout) |
| Temporal extent | Forecast init time → init + 240h |
| Assets | NetCDF file(s) per forecast run |
| Provider | NOAA/EPIC |

The MPC Pro team will handle STAC catalog creation and hosting, but we need to provide:
- **Data schema documentation** (variables, levels, grid specs)
- **Naming conventions** for blob paths
- **Update frequency** (every 6 hours)
- **Retention policy** (how many days of forecasts to keep)

#### 4. Authentication & Access
| Component | Method |
|---|---|
| AML → Blob Storage (write) | Managed Identity (AML workspace) or SAS token |
| MPC Pro → Blob Storage (read) | Configured by MPC Pro team |
| Public users → MPC Pro | Planetary Computer API (anonymous read) |

#### 5. Integration Steps (Sequence)
1. **Provision** a blob storage container for forecast outputs (coordinate with MPC Pro team)
2. **Configure** AML managed identity with `Storage Blob Data Contributor` role on that container
3. **Add upload step** to AML pipeline that writes NetCDF to blob after inference
4. **Provide** data schema + naming convention to MPC Pro team for STAC catalog setup
5. **MPC Pro team** configures ingestion pipeline to detect new blobs and update STAC catalog
6. **Validate** end-to-end: AML run → blob → MPC Pro → Planetary Computer API query

#### 6. Sample Output Upload Code
```python
from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential

credential = DefaultAzureCredential()
blob_service = BlobServiceClient(
    account_url="https://<mpc-storage-account>.blob.core.windows.net",
    credential=credential,
)
container_client = blob_service.get_container_client("nested-eagle-forecasts")

# Upload forecast NetCDF
blob_path = f"nested-eagle/v1/{timestamp:%Y/%m/%d/%H}/forecast.nc"
with open(local_forecast_path, "rb") as f:
    container_client.upload_blob(name=blob_path, data=f, overwrite=True)
```

---

## AML Endpoint Deployment

### Deployment Strategy: AML Pipeline (Batch) + Scheduled Trigger

Since the model runs every 6 hours on a schedule (not on-demand request/response), the recommended approach is an **AML Pipeline** with a **schedule trigger**, not a real-time managed endpoint.

| Approach | Fit | Reason |
|---|---|---|
| **AML Pipeline + Schedule** | ✅ Best fit | 6h cycle, multi-step (preproc → inference → upload), heterogeneous compute (CPU + GPU) |
| Managed Online Endpoint | ❌ Poor fit | Not request/response; long-running; wastes GPU when idle |
| Batch Endpoint | ⚠️ Possible | Works but Pipeline gives more control over multi-step orchestration |

### Pipeline Steps
```
Step 1: preproc (CPU compute)
  ├── Calculate NRT timestamp
  ├── Download GFS initial conditions → Zarr
  └── Download HRRR initial conditions → regrid to 6km → Zarr

Step 2: inference (GPU compute)
  ├── Load checkpoint from blob/model registry
  ├── Load initial conditions (Zarr from Step 1)
  └── Run eagle_inference → produce forecast output

Step 3: upload_to_mpc (CPU compute)
  ├── Convert output to NetCDF (if needed)
  └── Upload to MPC Pro blob storage container
```

### Schedule
```python
from azure.ai.ml import MLClient
from azure.ai.ml.entities import RecurrenceTrigger, JobSchedule

trigger = RecurrenceTrigger(
    frequency="hour",
    interval=6,
    start_time="2026-01-01T00:00:00Z",
    time_zone="UTC",
)
```

### AML Environment
- **Base image:** `mcr.microsoft.com/azureml/openmpi4.1.0-cuda11.8-cudnn8-ubuntu22.04`
- **Conda:** See `aml/environment/conda.yaml`
- **Key packages:** anemoi-inference 0.9.1, torch <2.7, flash-attn <2.8, eagle-tools, ufs2arco

### Workspace
An **existing AML workspace** for Eagle is already provisioned. The deployment should target that workspace.

---

## Pipeline Flow

```
Every 6 hours (00Z, 06Z, 12Z, 18Z)
│
▼
┌─────────────────────────────────────┐
│ 1. NRT Timestamp Calculation        │
│    floor(now, 6h) - 6h              │
│    e.g., now=14:30Z → IC=06Z        │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│ 2. Preprocessing (CPU)              │
│    - Fetch GFS from Planetary       │
│      Computer / NODD                │
│    - Fetch HRRR from Planetary      │
│      Computer / NODD                │
│    - Regrid HRRR → 6km              │
│    - Write Zarr initial conditions  │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│ 3. Inference (GPU - H100 80GB)      │
│    - Load checkpoint                │
│    - Load ICs (GFS + HRRR cutout)   │
│    - Run 40 autoregressive steps    │
│    - Output 240h forecast           │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│ 4. Post-processing & Upload         │
│    - Write NetCDF (CF-compliant)    │
│    - Upload to MPC Pro blob storage │
│    - Trigger STAC catalog update    │
└─────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│ Planetary Computer (Public Access)  │
│ Users query via STAC API            │
└─────────────────────────────────────┘
```

---

## Open Questions / Next Steps

### Questions Requiring Answers Before Deployment

---

#### Q1: What is the exact AML workspace name, subscription, and resource group for Eagle?
**Owner:** NOAA/EPIC team
**Priority:** 🔴 Blocking — must be answered first

**Why this matters:**
- All AML compute, environments, pipelines, and endpoints are deployed into a specific workspace. We cannot proceed with any deployment or testing without knowing which workspace to target.
- The workspace determines which Azure region we're in, which in turn determines GPU SKU availability (H100 is confirmed available).
- Network configuration (VNet, private endpoints) may already be set up on this workspace, which affects how we access blob storage and external data sources.
- We need the subscription ID and resource group to configure the Azure ML SDK client and set up RBAC permissions.

**What we need:**
- Workspace name
- Subscription ID
- Resource group name
- Azure region (e.g., East US, South Central US)
- Any existing compute clusters already provisioned

---

#### Q2: Has the MPC Pro storage account and container been provisioned for Nested-EAGLE output?
**Owner:** MPC Pro team
**Priority:** 🔴 Blocking for end-to-end pipeline

**Why this matters:**
- The final step of the AML pipeline uploads forecast NetCDF files to an Azure Blob Storage container that MPC Pro monitors. Without this container, we can build and test the pipeline but cannot validate the full end-to-end flow.
- We need the storage account name and container name to configure the upload step and set up authentication (Managed Identity or SAS token).
- The MPC Pro team may have specific requirements for blob path naming conventions, which affect how we structure the output. If we guess wrong, it requires rework.
- RBAC: The AML workspace's managed identity needs `Storage Blob Data Contributor` on this storage account. This is a cross-team permission grant.

**What we need:**
- Storage account name and URL
- Container name
- Required blob path naming convention (e.g., `nested-eagle/v1/{YYYY}/{MM}/{DD}/{HH}/forecast.nc`)
- Confirmation of auth method (Managed Identity preferred)
- Contact person on MPC Pro team for provisioning

---

#### Q3: Is `inference-last.ckpt` the correct/final checkpoint to use for production NRT?
**Owner:** NOAA/EPIC (Mariah Pope)
**Priority:** 🔴 Blocking for inference testing

**Why this matters:**
- The checkpoint file is the trained model. Using the wrong checkpoint means the forecasts are scientifically invalid.
- The POC `nested_eagle.yaml` references a generic `/path/to/checkpoint` with filename `inference-last.ckpt`. We need to confirm this is the intended production checkpoint, not a development/intermediate version.
- Checkpoint size directly affects GPU memory requirements and load time. If there are multiple checkpoints (e.g., different model versions, ensemble members), the pipeline and compute sizing may need adjustment.
- The checkpoint files are already uploaded to `eaglecheckpoints/eagle-checkpoints/poc/` — we need confirmation that those specific files are correct.
- We should also understand: will the checkpoint be updated over time as the model is retrained? If so, we need a versioning strategy (AML Model Registry is ideal for this).

**What we need:**
- Confirmation that the files in `eagle-checkpoints/poc/` are the production checkpoint
- Full list of files needed (is it just `inference-last.ckpt` or are there additional files?)
- Expected file size (for storage planning and download time estimation)
- Will there be future checkpoint updates? If so, how often?

---

#### Q4: Should HRRR/GFS initial conditions be pulled from Planetary Computer (NODD) or keep the current ufs2arco AWS sources?
**Owner:** Joint decision (NOAA/EPIC + Microsoft)
**Priority:** 🟡 Important — affects cost, latency, and reliability

**Why this matters:**
- The POC currently uses `aws_hrrr_archive` and `gfs_archive` sources in `ufs2arco`, which pull data from AWS S3 and NOAA archives. Running this from Azure means **cross-cloud data transfer**, which adds latency and egress costs.
- Both GFS and HRRR are **already available on Planetary Computer** via NODD:
  - GFS: `https://planetarycomputer.microsoft.com/dataset/noaa-gfs`
  - HRRR: `https://planetarycomputer.microsoft.com/dataset/noaa-hrrr`
- Using Planetary Computer data keeps everything in Azure, reducing latency and eliminating egress costs.
- However, switching data sources may require changes to `ufs2arco` configuration or code. The data format/structure may differ from what the current POC expects.
- Data availability timing matters for NRT: we need the data to be available within the 6-hour latency window. Need to confirm Planetary Computer's HRRR/GFS data freshness matches AWS sources.

**What we need:**
- Confirmation of data freshness/latency on Planetary Computer HRRR and GFS (is it available within ~3-4 hours of real-time?)
- Whether `ufs2arco` supports Planetary Computer as a source, or if adapter code is needed
- Decision on whether to use Planetary Computer from day one vs. migrate later

---

#### Q5: What is the retention policy for forecast outputs in MPC Pro?
**Owner:** NOAA/EPIC + MPC Pro team
**Priority:** 🟡 Important — affects storage costs and pipeline design

**Why this matters:**
- At 4 runs per day, forecast data accumulates rapidly. Each forecast covers 14 variables × 12 levels × 40 time steps across a global+CONUS grid — potentially **hundreds of MB to several GB per run**.
- Without a retention policy, storage costs grow unbounded. At ~1-5 GB/run × 4 runs/day = 4-20 GB/day = **120-600 GB/month**.
- The retention policy determines whether we need to implement automated cleanup (lifecycle management policies on blob storage) in the pipeline.
- It also affects downstream users: if someone is building workflows that depend on historical forecasts, they need to know how far back data will be available.
- MPC Pro may have its own policies or tiers (hot/cool/archive storage) that affect cost.

**What we need:**
- How many days/weeks of forecasts to retain in the hot tier?
- Should older forecasts be moved to cool/archive storage or deleted?
- Is there a separate long-term archive requirement?
- Who is responsible for implementing lifecycle policies?

---

#### Q6: Should the model output all variables or a subset?
**Owner:** NOAA/EPIC team
**Priority:** 🟡 Important — affects output size, upload time, and storage costs

**Why this matters:**
- The model produces forecasts for 14 atmospheric variables across 12 pressure levels plus surface fields. Writing all of them to NetCDF produces large files.
- Not all variables may be scientifically useful or validated for distribution. Distributing unvalidated variables could mislead end users.
- Subsetting variables reduces: file size, upload time to MPC Pro, storage costs, and download time for end users.
- The variable list also determines the NetCDF schema and STAC metadata, which MPC Pro needs to set up. Changing it later means updating the catalog.

**What we need:**
- List of variables to include in the public output
- Should output include all pressure levels or a subset?
- Should the output be a single NetCDF per forecast, or one file per variable/level?
- Are there any derived/diagnostic variables that should be computed post-inference?

The model's full variable set (from the GFS/HRRR configs):
```
Atmospheric (on 12 pressure levels): gh, u, v, w, t, q
Surface: sp, u10, v10, t2m, t_surface, sh2, lsm, orog
```

---

#### Q7: What NetCDF output conventions should be followed (CF metadata, compression, chunking)?
**Owner:** NOAA/EPIC team
**Priority:** 🟡 Important — affects interoperability and downstream tool compatibility

**Why this matters:**
- CF (Climate and Forecast) Conventions are the standard for geoscience NetCDF files. Proper CF metadata (`standard_name`, `units`, `coordinates`, `grid_mapping`) is required for tools like CDO, NCO, xarray, and QGIS to correctly interpret the data.
- MPC Pro's STAC catalog benefits from well-structured metadata — it can auto-extract temporal/spatial extent and variable information.
- Compression (e.g., zlib level 4-5) can reduce file sizes by 50-70% with minimal performance impact, significantly affecting upload time and storage costs.
- Chunking strategy affects read performance for users who want to access specific variables or time steps without downloading the full file.
- The nested grid structure (global GFS + CONUS HRRR cutout) may require special attention — are these written as separate grids in one file, or as separate files?

**What we need:**
- CF convention version to follow
- Variable naming convention (WMO standard, ECMWF convention, or custom)
- Units for each variable
- Compression settings (zlib level, shuffle filter)
- Global attributes (institution, source, model version, references)
- Grid mapping projection information (especially for the HRRR LAM grid)

---

#### Q8: What STAC collection schema and metadata fields are needed for MPC Pro?
**Owner:** MPC Pro team
**Priority:** 🟡 Important — must be resolved before MPC Pro can start ingesting

**Why this matters:**
- MPC Pro uses STAC (SpatioTemporal Asset Catalogs) to index, discover, and serve data. The STAC schema defines how users find and access Nested-EAGLE forecasts through the Planetary Computer API.
- The schema must be defined before MPC Pro can configure their ingestion pipeline. Without it, data will land in blob storage but won't be discoverable.
- Key decisions: Should each 6h forecast run be a separate STAC item? Should individual variables be separate assets within an item? What temporal extent representation is used (init time vs. valid times)?
- The Nested-EAGLE grid is unusual — it's a nested cutout (high-res CONUS inside a global grid). How this is represented in STAC geometry affects spatial search queries.

**What we need:**
- STAC collection definition (collection ID, description, license, providers)
- STAC item structure (one item per forecast run? per variable?)
- Spatial extent representation (global bbox, CONUS bbox, or both?)
- Temporal extent (forecast initialization time? valid time range?)
- Asset naming and roles
- Any additional STAC extensions (forecast extension, datacube extension?)
- Example STAC item JSON for review

---

#### Q9: GPU SKU validation — Confirm compute sizing with actual checkpoint before production
**Owner:** Microsoft (deployment team) + NOAA/EPIC (provide checkpoint)
**Priority:** 🔴 Blocking for production — required before committing to a SKU

**Why this matters:**
- The H100 80GB is confirmed as the production GPU. Peak VRAM usage should be monitored during initial runs to document headroom.
- Choosing too small a GPU → out-of-memory (OOM) errors during production runs, pipeline failures.
- Peak VRAM usage occurs during the autoregressive inference loop — all 40 steps of the 240h forecast must complete without OOM. H100 80GB provides ample headroom.

**Validation plan:**
1. GPU compute `eagle-gpu-h100` is already provisioned
2. Download the checkpoint from `eaglecheckpoints/eagle-checkpoints/poc/`
3. Generate the `hrrr_06km.nc` static grid file
4. Run a single end-to-end forecast (preproc → inference)
5. Monitor GPU metrics: peak VRAM usage, inference wall-clock time
6. Document peak VRAM and run time

**What we need before this can happen:**
- Access to the Eagle AML workspace (Q1)
- Confirmed checkpoint files (Q3)
- GPU quota approved in the workspace region for the target SKU

---

#### Q10: What is the NRT latency requirement, and what happens if a run fails or data is late?
**Owner:** NOAA/EPIC team
**Priority:** 🟡 Important — affects pipeline reliability design

**Why this matters:**
- The POC hardcodes a 6-hour latency (`nrt_latency="6h"` in `utils.py`). This means if the pipeline runs at 12Z, it processes the 06Z initialization. This gives a 6-hour window for input data to become available.
- In production, GFS and HRRR data can occasionally be delayed. If the initial conditions aren't available when the pipeline triggers, the run will fail.
- We need to decide: Should the pipeline retry? Wait? Fall back to older ICs? Alert and skip?
- Monitoring and alerting are critical for NRT operations — stakeholders need to know when forecasts are delayed or missing.

**What we need:**
- Maximum acceptable delay for a forecast cycle
- Retry strategy (how many retries, backoff interval)
- Failure notification requirements (email, Teams, PagerDuty?)
- Is there a degraded-mode option (e.g., run with GFS-only if HRRR is late)?

---

#### Q11: Authentication and network access — How does the AML workspace access external data and output storage?
**Owner:** Microsoft (deployment team) + NOAA/EPIC (workspace admin)
**Priority:** 🟡 Important — can block deployment if not addressed early

**Why this matters:**
- The AML compute needs outbound internet access to fetch GFS/HRRR data (from Planetary Computer or AWS)
- The AML compute needs access to `eaglecheckpoints` blob storage for the checkpoint
- The AML compute needs write access to the MPC Pro output blob storage
- If the Eagle AML workspace is behind a VNet or has private endpoints, additional network configuration (NSGs, private endpoints, service endpoints) may be required
- Managed Identity is the preferred authentication method (no secrets to manage), but it requires RBAC role assignments across potentially different subscriptions

**What we need:**
- Is the Eagle AML workspace VNet-integrated?
- Are there firewall rules or NSGs that restrict outbound access?
- Can we use the workspace's managed identity, or is a separate service principal required?
- Cross-subscription access: is the MPC Pro storage in the same subscription as the Eagle workspace?

---

#### Q12: Will the model be retrained or updated, and how should model versioning work?
**Owner:** NOAA/EPIC team
**Priority:** 🟢 Not blocking, but important for long-term operations

**Why this matters:**
- If the Nested-EAGLE model is periodically retrained, we need a process to update the checkpoint in the pipeline without downtime.
- AML Model Registry provides versioning, lineage tracking, and easy rollback — but only if we set it up from the start.
- New model versions may require different conda environments (e.g., newer anemoi-inference version), which means environment updates too.
- Output consumers (MPC Pro users) may need to know which model version produced a given forecast.

**What we need:**
- Expected frequency of model updates
- Versioning scheme (v1, v2, ... or date-based?)
- Should old model versions remain available for comparison?
- Should model version be included in output metadata/blob paths?

---

### Summary: Question Priority Matrix

| Priority | Questions | Status |
|---|---|---|
| 🔴 **Blocking** | Q1 (AML workspace), Q3 (checkpoint), Q9 (GPU validation) | Must answer before any deployment |
| 🔴 **Blocking E2E** | Q2 (MPC Pro storage) | Must answer before end-to-end test |
| 🟡 **Important** | Q4 (data source), Q5 (retention), Q6 (variables), Q7 (NetCDF), Q8 (STAC), Q10 (latency/failure), Q11 (auth/network) | Must answer before production |
| 🟢 **Long-term** | Q12 (versioning) | Should answer before ongoing operations |

### Suggested Meeting Agenda

Given these questions, the upcoming meeting should cover:

1. **AML Workspace Access** (Q1, Q11) — 10 min
   - Get workspace details, confirm access for deployment team
2. **Checkpoint & Model Details** (Q3, Q9) — 10 min
   - Confirm checkpoint, plan GPU validation test
3. **Data Sources** (Q4) — 10 min
   - Decide Planetary Computer vs. AWS for HRRR/GFS
4. **MPC Pro Integration** (Q2, Q5, Q6, Q7, Q8) — 15 min
   - Storage provisioning, output schema, STAC setup
5. **Operations & Reliability** (Q10, Q12) — 10 min
   - Failure handling, versioning, monitoring
6. **Next Steps & Timeline** — 5 min

### WoFSCast Note
WoFSCast is a **separate effort** in a different subscription/workspace. MPC Pro integration is scoped to **Nested-EAGLE only** at this time. If the WoFSCast team (Joshua/Corey) sees value in MPC Pro later, that would be a separate engagement.

---

## Deployment Plan

### Prerequisites (Must Be Resolved Before Implementation)

These are **customer/partner dependencies** — implementation cannot start until all three are confirmed:

| # | Prerequisite | Owner | Status |
|---|---|---|---|
| P1 | AML workspace access (name, subscription, region, resource group) | NOAA/EPIC team | ⬜ Pending |
| P2 | Checkpoint confirmation (`eagle-checkpoints/poc/` files are correct) | NOAA/EPIC (Mariah Pope) | ⬜ Pending |
| P3 | MPC Pro blob storage provisioned (account, container, naming convention) | Planetary Computer team | ⬜ Pending |

### Items to Clarify with Customer Before Implementation

| # | Item | Why it matters | Ask who |
|---|---|---|---|
| C1 | GPU quota — H100 quota confirmed (`eagle-gpu-h100` provisioned) | Compute is ready. | NOAA workspace admin |
| C2 | Is the workspace VNet-integrated or behind firewalls? | Affects outbound access to Planetary Computer and blob storage. | NOAA workspace admin |
| C3 | Can we use the workspace managed identity for blob access? | Determines auth approach for checkpoint + MPC Pro storage. | NOAA workspace admin |
| C4 | Does NOAA want Planetary Computer as the HRRR/GFS source, or keep AWS? | Affects egress cost (~$32-86/mo), latency, and whether ufs2arco needs changes. | Joint decision |
| C5 | What variables to include in public output? All 14 or a subset? | Affects file size, storage cost, STAC schema. | NOAA/EPIC science team |
| C6 | Who generates virtual Zarr references — MPC Pro or us? | Determines if we need a Kerchunk step in the pipeline. | MPC Pro team |
| C7 | Interest in Foundry model catalog listing? | If yes, separate engagement needed. Does not block NRT pipeline. | NOAA/EPIC leadership |

### Implementation as AML Pipeline Job (Not Endpoint)

The model runs on a **fixed 6h schedule**, not on-demand request/response. This dictates the implementation pattern:

| Approach | Fit | Why |
|---|---|---|
| **AML Pipeline Job + Schedule** | ✅ Best fit | 6h cycle; multi-step (CPU → GPU → CPU); 30-70 min runtime; scale-to-zero between runs |
| Managed Online Endpoint | ❌ | Not request/response; 30-70 min is too long; GPU idles 22+ hrs/day |
| Batch Endpoint | ⚠️ Future option | Could wrap the pipeline for on-demand requests later |

### GPU Quota Check Process

Before provisioning compute, verify quota in the Eagle workspace:

```bash
# 1. Check current quota allocation
az ml compute list-usage \
  --workspace-name <eagle-workspace> \
  --resource-group <rg> \
  -o table

# 2. Check which GPU SKUs are available in the region
az vm list-skus --location <region> \
  --resource-type virtualMachines \
  --query "[?contains(name, 'NC')].[name, restrictions]" -o table

# H100 quota confirmed — eagle-gpu-h100 already provisioned
```

Quota requests take **1-5 business days**. Submit as early as possible.

---

## Milestone Plan

### Milestone 1: Validate & First Forecast (~1-2 weeks after prerequisites met)

**Goal:** Confirm the model runs end-to-end on AML and produces a valid forecast.

| Step | Task | Compute | Dependency |
|---|---|---|---|
| 1.1 | Get AML workspace credentials and verify access | Local | P1 |
| 1.2 | Check GPU quota; submit increase request if needed | Local | P1 |
| 1.3 | Register checkpoint in AML Model Registry | Local → AML | P1, P2 |
| 1.4 | Generate `hrrr_06km.nc` static grid file (one-time) | AML CPU | 1.3 |
| 1.5 | Provision CPU compute cluster (`eagle-cpu`, D16s_v5, scale-to-zero) | AML | 1.2 |
| 1.6 | Provision GPU compute cluster (`eagle-gpu-h100`, H100 80GB, scale-to-zero) | AML | 1.2 (quota confirmed) |
| 1.7 | Build AML environment (Docker + conda) | AML | — |
| 1.8 | Run preprocessing test (download GFS + HRRR, regrid) | AML CPU | 1.5, 1.7 |
| 1.9 | Run inference test on H100 — measure peak VRAM and wall-clock time | AML GPU | 1.6, 1.8 |
| 1.10 | Validate output NetCDF (format, variables, CF metadata, chunking) | AML CPU | 1.9 |
| 1.11 | Monitor H100 VRAM headroom for documentation | AML GPU | 1.9 |

**Output:** Validated GPU SKU, confirmed runtime, sample forecast NetCDF.

### Milestone 2: AML Pipeline & MPC Pro Integration (~1-2 weeks)

**Goal:** Full automated pipeline that uploads to Planetary Computer.

| Step | Task | Compute | Dependency |
|---|---|---|---|
| 2.1 | Build AML pipeline (3 steps: preproc → inference → upload) | AML | M1 complete |
| 2.2 | Create `upload_to_mpc.py` script (blob upload with managed identity) | Code | P3 |
| 2.3 | Configure RBAC: workspace managed identity → `Storage Blob Data Contributor` on MPC blob | AML + Azure | P3, C3 |
| 2.4 | Test manual pipeline run end-to-end | AML | 2.1, 2.2, 2.3 |
| 2.5 | Validate NetCDF lands in MPC blob correctly | Azure | 2.4 |
| 2.6 | MPC Pro team validates virtual Zarr reference generation | MPC Pro | 2.5 |
| 2.7 | MPC Pro team creates STAC catalog entry (`noaa-nested-eagle`) | MPC Pro | 2.5 |
| 2.8 | Validate end-to-end: pipeline → blob → virtual Zarr → STAC → PC API query | All | 2.6, 2.7 |
| 2.9 | **(Cost opt)** Add NetCDF compression (zlib level 4-5) | Code | 2.4 |
| 2.10 | **(Cost opt)** Evaluate switching to PC HRRR/GFS source (eliminate AWS egress) | Code/Config | C4 |

**Output:** Working end-to-end pipeline with forecasts visible on Planetary Computer.

### Milestone 3: Production & Scheduling (~1 week)

**Goal:** Automated 6h NRT operations with monitoring.

| Step | Task | Compute | Dependency |
|---|---|---|---|
| 3.1 | Enable 6h schedule trigger (RecurrenceTrigger) | AML | M2 complete |
| 3.2 | Run 24h burn-in (4 consecutive cycles) | AML | 3.1 |
| 3.3 | Set up monitoring (pipeline failure alerts) | AML + Azure Monitor | 3.1 |
| 3.4 | Implement retry logic for data availability | Code | 3.1 |
| 3.5 | Set storage lifecycle policy (retention: 30/60/90 days TBD) | Azure Blob | M2 complete |
| 3.6 | **(Cost opt)** Evaluate low-priority/spot GPU for non-critical cycles | AML | 3.2 |
| 3.7 | Document runbook (manual intervention procedures) | Docs | 3.2 |

**Output:** Production NRT system running every 6h, public forecasts on Planetary Computer.

### Milestone 4: Foundry & Optimization (Separate Scope)

**Goal:** Optional enhancements — separate from NRT pipeline delivery.

| Step | Task | Dependency |
|---|---|---|
| 4.1 | Evaluate listing in Azure AI Foundry model catalog | C7, NOAA approval |
| 4.2 | Prepare model card, documentation, evaluation benchmarks | 4.1 |
| 4.3 | Engage Foundry catalog team for onboarding | 4.2 |
| 4.4 | Switch HRRR/GFS source to Planetary Computer (if not done in M2) | C4 |
| 4.5 | Add Zarr output option (physical, not virtual) if needed | User demand |

**Note:** Milestone 4 is **separate scope**. AML Model Registry (used in M1) is NOT the same as Foundry catalog. The registry is a workspace-internal tool for versioning — it's part of the standard pipeline. Foundry catalog is a public listing requiring a separate partnership engagement.

---

## Virtual Zarr: Code Changes Required

**On our side: likely none.** The pipeline outputs NetCDF → MPC Pro generates virtual Zarr references.

However, for optimal virtual Zarr performance, validate during Milestone 1 (step 1.10):

| Check | What to verify | Fix if needed |
|---|---|---|
| File format | Output is NetCDF4/HDF5 (not NetCDF3 classic) | Anemoi default is HDF5 ✅ |
| Chunked storage | NetCDF has internal chunking | Add `encoding` parameter at write time |
| CF metadata | `standard_name`, `units`, `coordinates` present | Add lightweight post-processing step |

If chunking is needed (only change we might make):
```python
# Add chunking to NetCDF output for efficient byte-range reads
encoding = {var: {"chunksizes": (1, nlat, nlon)} for var in ds.data_vars}
ds.to_netcdf("forecast.nc", engine="h5netcdf", encoding=encoding)
```

This is a one-line addition, not a pipeline redesign.

---

## Cost Optimization Plan

### Optimizations by Impact

| # | Optimization | Monthly Savings | Effort | Milestone |
|---|---|---|---|---|
| O1 | **Scale-to-zero compute** (min_instances=0) | ~$2,500 vs always-on GPU | None — built into design | M1 |
| O2 | **Use PC HRRR/GFS** instead of AWS | ~$32-86 (eliminate egress) | Medium — validate PC data freshness, possible ufs2arco adapter | M2/M4 |
| O3 | **H100 confirmed** — A100 not available | N/A | N/A — decided | M1 |
| O4 | **NetCDF compression** (zlib level 4-5) | ~$5-15 (50-70% storage reduction) | Low — one encoding param | M2 |
| O5 | **Storage lifecycle policy** (30-day retention) | Prevents unbounded growth | Low — one Azure policy | M3 |
| O6 | **Spot/low-priority GPU** for non-critical cycles | ~60-80% GPU discount | Low config change, higher failure risk | M3 |
| O7 | **Parallel GFS+HRRR download** in preprocessing | ~10-15 min faster (less CPU time billed) | Medium — refactor preproc.py | M4 |

### Cost Scenarios (Monthly)

| Scenario | GPU | Data Source | Compression | Lifecycle | Monthly Cost |
|---|---|---|---|---|---|
| **Unoptimized** | H100 80GB | AWS (egress) | None | None | ~$350-840+ |
| **After M1** (H100 confirmed) | H100 80GB | AWS (egress) | None | None | ~$178 |
| **After M2** (PC data + compression) | H100 80GB | PC (free) | zlib | None | ~$140-155 |
| **After M3** (lifecycle + spot) | H100 spot | PC (free) | zlib | 30-day | ~$55-75 |

### Key Insight
The single biggest cost saving is **already built in**: scale-to-zero. Without it, an always-on A100 costs ~$2,640/month. With scale-to-zero and ~2-5 hrs/day actual usage, it drops to ~$110/month. Everything else is optimization on top of that.

---

## Dependency Graph

```
P1 (AML workspace) ─────┬──▶ 1.1 (verify access)
                         ├──▶ 1.2 (check quota) ──▶ 1.5/1.6 (provision compute)
                         │
P2 (checkpoint)    ──────┼──▶ 1.3 (register model) ──▶ 1.9 (test inference)
                         │
P3 (MPC storage)   ──────┼──▶ 2.2 (upload script) ──▶ 2.4 (e2e test)
                         │
1.7 (environment)  ──────┼──▶ 1.8 (preproc test) ──▶ 1.9 (inference test)
                         │
1.9 (inference OK) ──────┼──▶ 2.1 (build pipeline) ──▶ 3.1 (schedule)
                         │
2.8 (e2e validated)──────┴──▶ 3.1 (production schedule) ──▶ 3.2 (burn-in)
```

**Critical path:** P1 → 1.2 → quota approved → 1.6 → 1.9 → 2.1 → 2.4 → 3.1

The longest-lead item is **GPU quota approval** (1-5 business days). Submit the request the moment we have workspace access.
