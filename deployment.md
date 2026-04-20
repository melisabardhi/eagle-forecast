# Nested-EAGLE NRT: Deployment Plan

## Prerequisites (Must Be Resolved Before Implementation Starts)

| # | Prerequisite | Owner | Status | Notes |
|---|---|---|---|---|
| **P1** | AML workspace access (name, subscription, region, resource group) | NOAA/EPIC team | ⬜ Pending | All compute and pipelines deploy here |
| **P2** | Checkpoint confirmation (`eagle-checkpoints/poc/` files are correct) | NOAA/EPIC (Mariah Pope) | ⬜ Pending | Wrong checkpoint = invalid forecasts |
| **P3** | MPC Pro blob storage provisioned (account, container, naming convention) | Planetary Computer team | ⬜ Pending | Pipeline uploads NetCDF here |

---

## Items to Clarify with Customer

| # | Item | Why it matters | Ask who |
|---|---|---|---|
| C1 | GPU quota — confirm H100 quota is sufficient in the workspace region | Cannot provision compute without quota. Customer has H100 available. | NOAA workspace admin |
| C2 | Is the workspace VNet-integrated or behind firewalls? | Affects outbound access to Planetary Computer and blob storage. | NOAA workspace admin |
| C3 | Can we use the workspace managed identity for blob access? | Determines auth approach for checkpoint + MPC Pro storage. | NOAA workspace admin |
| C4 | Planetary Computer as HRRR/GFS source, or keep AWS? | Affects egress cost (~$32-86/mo), latency, and ufs2arco config. | Joint decision |
| C5 | What variables to include in public output? All 14 or a subset? | Affects file size, storage cost, STAC schema. | NOAA/EPIC science team |
| C6 | Who generates virtual Zarr references — MPC Pro or us? | Determines if we need a Kerchunk step in the pipeline. | MPC Pro team |
| C7 | Interest in Foundry model catalog listing? | If yes, separate engagement. Does not block NRT pipeline. | NOAA/EPIC leadership |

---

## Deployment Type: AML Pipeline Job (Not Endpoint)

| Approach | Fit | Reason |
|---|---|---|
| **AML Pipeline Job + Schedule** | ✅ Best fit | 6h cycle; 2-step (CPU → GPU); 30-70 min runtime; scale-to-zero |
| Managed Online Endpoint | ❌ | Not request/response; too long; GPU idles 22+ hrs/day |
| Batch Endpoint | ⚠️ Future | Could wrap same pipeline for on-demand requests later |

**2-Step Pipeline:**
- **Step 1 (CPU command job):** Preprocessing — download GFS/HRRR, regrid, write Zarr to shared datastore
- **Step 2 (GPU command job):** Inference + upload — load checkpoint, run forecast, write NetCDF, upload to MPC Pro blob

Upload runs on the GPU node since the output is already in local storage. The ~$0.58 cost of H100 time for upload is less than the complexity of a third step and data transfer.

---

## Step 0: Set Up VS Code + Azure ML SDK (Mariah's Local Machine)

**Goal:** Get Mariah's dev environment ready to run AML SDK commands from VS Code.

### 0.1 — Install VS Code Extensions
Open VS Code → Extensions panel (`Ctrl+Shift+X`) → Install:
- **Python** (Microsoft) — Python language support
- **Azure Machine Learning** (Microsoft) — browse workspace, compute, jobs from VS Code sidebar
- **Azure Account** (Microsoft) — sign-in to Azure from VS Code
- **Jupyter** (Microsoft) — run Python notebooks inline (useful for testing SDK calls)

### 0.2 — Install Azure CLI
- Download from: https://learn.microsoft.com/en-us/cli/azure/install-azure-cli
- After install, open VS Code terminal (`Ctrl+``) and verify:
  ```bash
  az --version
  ```
- Install the ML extension:
  ```bash
  az extension add -n ml
  ```

### 0.3 — Sign In to Azure
```bash
az login
```
- This opens a browser — sign in with the account that has access to the Eagle AML workspace
- Set the correct subscription:
  ```bash
  az account set --subscription "<SUBSCRIPTION_ID>"
  ```
- Verify:
  ```bash
  az account show --query "{name:name, id:id}" -o table
  ```

### 0.4 — Create a Python Environment
- In VS Code terminal:
  ```bash
  python -m venv .venv
  ```
- Activate it:
  - **Windows:** `.venv\Scripts\activate`
  - **Mac/Linux:** `source .venv/bin/activate`
- Install the AML SDK + Azure Identity:
  ```bash
  pip install azure-ai-ml azure-identity azure-storage-blob
  ```

### 0.5 — Create a Setup Script
- Create a file `aml/setup_client.py` in the repo with:
  ```python
  from azure.ai.ml import MLClient
  from azure.identity import DefaultAzureCredential

  # --- FILL IN AFTER GETTING WORKSPACE DETAILS (P1) ---
  SUBSCRIPTION_ID = "<SUBSCRIPTION_ID>"
  RESOURCE_GROUP = "<RESOURCE_GROUP>"
  WORKSPACE_NAME = "<WORKSPACE_NAME>"

  credential = DefaultAzureCredential()
  ml_client = MLClient(
      credential=credential,
      subscription_id=SUBSCRIPTION_ID,
      resource_group_name=RESOURCE_GROUP,
      workspace_name=WORKSPACE_NAME,
  )

  # Quick test — should print workspace info
  ws = ml_client.workspaces.get(ml_client.workspace_name)
  print(f"Connected to workspace: {ws.name}")
  print(f"  Region: {ws.location}")
  print(f"  Resource group: {ws.resource_group}")
  ```
- Run it:
  ```bash
  python aml/setup_client.py
  ```
- If this prints the workspace info, the SDK is working and authenticated.

### 0.6 — Verify from VS Code Azure ML Extension
- Click the **Azure** icon in the VS Code sidebar
- Expand **Machine Learning** → find the Eagle workspace
- You should see: Compute, Environments, Models, Jobs, Data sections
- This gives a UI view alongside the SDK — useful for monitoring jobs

### Troubleshooting
| Problem | Fix |
|---|---|
| `az login` fails | Check network/proxy — may need `az login --use-device-code` behind corporate firewall |
| `DefaultAzureCredential` fails | Run `az login` first — the SDK uses the CLI token. Or try `AzureCliCredential()` explicitly |
| Can't see workspace in VS Code extension | Check subscription filter — click "Select Subscriptions" in the Azure sidebar |
| `pip install` fails for `azure-ai-ml` | Make sure the venv is activated. Try `pip install --upgrade pip` first |
| Permission denied on workspace | Need RBAC role: at minimum `AzureML Data Scientist` on the workspace |

---

## Milestone 1: Validate & First Forecast

**Goal:** Confirm the model runs end-to-end on AML and produces a valid forecast.
**Timeline:** ~1-2 weeks after prerequisites met.

### Steps

#### 1.1 — Get AML workspace access
- Receive workspace name, subscription ID, resource group, region from NOAA team
- Update `aml/setup_client.py` with the real values
- Run it to confirm the connection works:
  ```bash
  python aml/setup_client.py
  ```
- If it prints workspace info, you're connected
- **Depends on:** P1, Step 0 (VS Code + SDK set up)

#### 1.2 — Check H100 GPU quota
- In VS Code terminal:
  ```bash
  az ml compute list-usage \
    --workspace-name <eagle-workspace> \
    --resource-group <rg> \
    -o table | findstr -i "NCads"
  ```
- Or check in **Azure Portal → Subscriptions → Usage + quotas** → filter for `NC40adsH100v5`
- Verify at least 40 cores allocated for `NC40ads_H100_v5` family
- If quota needs increase, submit request via Portal → Support → Quota (takes 1-5 business days)
- **Depends on:** P1

#### 1.3 — Register checkpoint in AML Model Registry
- First, create a datastore pointing to the checkpoint blob storage:
  ```bash
  az ml datastore create \
    --name eagle-checkpoints \
    --type azure_blob \
    --account-name eaglecheckpoints \
    --container-name eagle-checkpoints \
    --resource-group <rg> \
    --workspace-name <workspace>
  ```
- Then register the checkpoint as a model:
  ```python
  from azure.ai.ml.entities import Model

  model = Model(
      name="nested-eagle",
      version="1",
      path="azureml://datastores/eagle-checkpoints/paths/poc/inference-last.ckpt",
      type="custom_model",
      description="Nested-EAGLE NRT weather forecast model",
      tags={"framework": "anemoi-inference", "grid": "nested-cutout-6km", "lead_time": "240h"},
  )
  ml_client.models.create_or_update(model)
  ```
- Verify in VS Code: Azure sidebar → ML → Models → should see `nested-eagle` version 1
- **Depends on:** P1, P2

#### 1.4 — Generate static grid file (one-time)
- Run `poc/config/hrrr_6km.py` locally (or on an AML CPU job) to create `hrrr_06km.nc`
- Upload to the datastore:
  ```bash
  az storage blob upload \
    --account-name eaglecheckpoints \
    --container-name eagle-checkpoints \
    --name poc/hrrr_06km.nc \
    --file hrrr_06km.nc
  ```
- This only needs to be done once
- **Depends on:** 1.3

#### 1.5 — Provision CPU compute cluster
- In VS Code terminal, create a Python script or run interactively:
  ```python
  from azure.ai.ml.entities import AmlCompute

  cpu_cluster = AmlCompute(
      name="eagle-cpu",
      type="amlcompute",
      size="Standard_D16s_v5",
      min_instances=0,               # Scale to zero — no cost when idle
      max_instances=1,
      idle_time_before_scale_down=300,  # 5 min idle → scale down
  )
  ml_client.compute.begin_create_or_update(cpu_cluster)
  print("CPU cluster 'eagle-cpu' created (scale-to-zero)")
  ```
- Verify: Azure sidebar → ML → Compute → should see `eagle-cpu`
- **Depends on:** 1.2

#### 1.6 — Provision GPU compute cluster
  ```python
  gpu_cluster = AmlCompute(
      name="eagle-gpu-h100",
      type="amlcompute",
      size="Standard_NC40ads_H100_v5",  # H100 80GB — provisioned
      min_instances=0,                   # Scale to zero
      max_instances=1,
      idle_time_before_scale_down=300,
  )
  ml_client.compute.begin_create_or_update(gpu_cluster)
  print("GPU cluster 'eagle-gpu-h100' (H100 80GB) created (scale-to-zero)")
  ```
- Verify: Azure sidebar → ML → Compute → should see `eagle-gpu-h100`
- **Depends on:** 1.2 (H100 quota must be confirmed)

#### 1.7 — Build and register AML environment
- Environment files are in `aml/environment/` (Dockerfile + conda.yaml)
- Register:
  ```python
  from azure.ai.ml.entities import Environment

  env = Environment(
      name="eagle-nrt",
      build={"path": "aml/environment/"},
      description="Nested-EAGLE NRT environment: anemoi-inference, torch, flash-attn",
  )
  ml_client.environments.create_or_update(env)
  print("Environment 'eagle-nrt' registered — Docker build will start on first job")
  ```
- Note: The Docker image builds on first use (takes ~10-15 min the first time)
- Verify: Azure sidebar → ML → Environments → should see `eagle-nrt`
- **Depends on:** none (can do in parallel with compute steps)

#### 1.8 — Test preprocessing (CPU command job)
- Submit a command job:
  ```python
  from azure.ai.ml import command, Input

  preproc_job = command(
      code="./poc",
      command="python preproc.py",
      environment="eagle-nrt:1",
      compute="eagle-cpu",
      display_name="eagle-preproc-test",
      experiment_name="nested-eagle-nrt",
  )
  returned_job = ml_client.jobs.create_or_update(preproc_job)
  print(f"Job submitted: {returned_job.studio_url}")
  ```
- Click the studio URL to monitor in the AML UI, or watch in VS Code Azure sidebar → Jobs
- Validate:
  - GFS downloads successfully and converts to Zarr
  - HRRR downloads, regrids to 6km, converts to Zarr
  - Note the wall-clock time
- **Depends on:** 1.5, 1.7

#### 1.9 — Test inference (GPU command job)
- Submit a command job to the H100 cluster:
  ```python
  inference_job = command(
      code="./poc",
      command="python inference.py",
      environment="eagle-nrt:1",
      compute="eagle-gpu-h100",
      display_name="eagle-inference-test",
      experiment_name="nested-eagle-nrt",
  )
  returned_job = ml_client.jobs.create_or_update(inference_job)
  print(f"Job submitted: {returned_job.studio_url}")
  ```
- Monitor GPU usage during the run (check from AML Studio → Job → Monitoring tab)
- Record:
  - Peak VRAM usage (GB)
  - Wall-clock time for 40 autoregressive steps
  - Any OOM errors
- **Depends on:** 1.6, 1.8

#### 1.10 — Validate output NetCDF
- Download the output from the job and inspect:
  ```python
  import xarray as xr
  ds = xr.open_dataset("forecast.nc")
  print(ds)                    # Variables, dimensions, coordinates
  print(ds.attrs)              # Global attributes (CF metadata?)
  print(ds.encoding)           # Chunking, compression
  ```
- Verify:
  - Format is NetCDF4/HDF5 (not NetCDF3) — needed for virtual Zarr
  - Variables match expected output (14 atmospheric + surface)
  - Dimensions correct (time steps, lat, lon, level)
  - CF metadata present (or document what's missing)
- **Depends on:** 1.9

#### 1.11 — (Cost optimization) Test on smaller GPU
- H100 80GB confirmed as production GPU (`eagle-gpu-h100`)
- Monitor peak VRAM for documentation
- **Depends on:** 1.9

### Milestone 1 Output
- ✅ VS Code + AML SDK working and authenticated
- ✅ Confirmed H100 GPU and peak VRAM documented
- ✅ Confirmed runtime (preproc + inference)
- ✅ Sample forecast NetCDF for MPC Pro team to review
- ✅ AML environment, compute, and model registry set up

---

## Milestone 2: AML Pipeline & MPC Pro Integration

**Goal:** Full automated pipeline that uploads to Planetary Computer.
**Timeline:** ~1-2 weeks after M1.

### Steps

#### 2.1 — Build AML pipeline (2 steps)
- Define 2-step pipeline using AML v2 SDK:
  ```python
  @dsl.pipeline(name="nested-eagle-nrt")
  def nested_eagle_pipeline():
      step1 = preprocess_step()                                    # CPU cluster
      step2 = inference_and_upload_step(ics=step1.outputs.initial_conditions)  # GPU cluster
  ```
- Step 1 (CPU): download GFS/HRRR, regrid, write Zarr to shared datastore
- Step 2 (GPU): load checkpoint + ICs, run inference, write NetCDF, upload to MPC Pro blob
- Upload stays on GPU node — output is already local, avoids data transfer overhead
- **Depends on:** M1 complete

#### 2.2 — Add upload logic to inference script
- Add blob upload to the end of the GPU inference script (runs on same node):
  ```python
  from azure.storage.blob import BlobServiceClient
  from azure.identity import DefaultAzureCredential
  
  credential = DefaultAzureCredential()
  blob_service = BlobServiceClient(
      account_url="https://<mpc-storage>.blob.core.windows.net",
      credential=credential,
  )
  container = blob_service.get_container_client("<container-name>")
  
  blob_path = f"nested-eagle/v1/{timestamp:%Y/%m/%d/%H}/forecast.nc"
  with open(local_path, "rb") as f:
      container.upload_blob(name=blob_path, data=f, overwrite=True)
  ```
- **Depends on:** P3 (need storage account name and container)

#### 2.3 — Configure RBAC
- Grant AML workspace managed identity `Storage Blob Data Contributor` on:
  - MPC Pro output storage account
  - `eaglecheckpoints` storage account (if not already)
  ```bash
  az role assignment create \
    --assignee <workspace-managed-identity-object-id> \
    --role "Storage Blob Data Contributor" \
    --scope /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Storage/storageAccounts/<mpc-storage>
  ```
- **Depends on:** P3, C3

#### 2.4 — Test manual pipeline run
- Submit pipeline manually:
  ```python
  pipeline_job = ml_client.jobs.create_or_update(
      nested_eagle_pipeline(),
      experiment_name="nested-eagle-nrt",
  )
  print(f"Pipeline: {pipeline_job.studio_url}")
  ```
- Monitor both steps complete successfully
- **Depends on:** 2.1, 2.2, 2.3

#### 2.5 — Validate blob output
- Confirm NetCDF landed in MPC Pro blob:
  ```bash
  az storage blob list \
    --account-name <mpc-storage> \
    --container-name <container> \
    --prefix "nested-eagle/v1/" \
    --output table
  ```
- **Depends on:** 2.4

#### 2.6 — MPC Pro validates virtual Zarr
- Hand off to MPC Pro team
- They run Kerchunk/VirtualiZarr against the NetCDF
- Confirm virtual references work:
  ```python
  import xarray as xr
  ds = xr.open_zarr("reference://", storage_options={"fo": "reference.json"})
  print(ds)  # Should match the original NetCDF
  ```
- **Depends on:** 2.5

#### 2.7 — MPC Pro creates STAC catalog
- MPC Pro team creates:
  - STAC collection: `noaa-nested-eagle`
  - STAC items: one per forecast cycle
  - Assets: NetCDF + virtual Zarr reference
- **Depends on:** 2.5

#### 2.8 — End-to-end validation
- Verify full chain:
  ```
  AML pipeline run → blob → virtual Zarr → STAC → Planetary Computer API query
  ```
- Test user access:
  ```python
  import planetary_computer
  import pystac_client
  
  catalog = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
  results = catalog.search(collections=["noaa-nested-eagle"])
  items = list(results.items())
  print(f"Found {len(items)} forecast items")
  ```
- **Depends on:** 2.6, 2.7

#### 2.9 — (Cost optimization) Add NetCDF compression
- Add zlib compression to output:
  ```python
  encoding = {var: {"zlib": True, "complevel": 4, "shuffle": True} for var in ds.data_vars}
  ds.to_netcdf("forecast.nc", encoding=encoding)
  ```
- Reduces file size by 50-70%, saves storage and upload time
- **Depends on:** 2.4

#### 2.10 — (Cost optimization) Evaluate PC data source
- If C4 is resolved and NOAA agrees to use Planetary Computer:
  - Test data freshness (available within 3-4 hours of real-time?)
  - Adapt `ufs2arco` config or write adapter
  - Eliminates AWS egress cost (~$32-86/month)
- **Depends on:** C4

### Milestone 2 Output
- ✅ Working 2-step AML pipeline (CPU preproc → GPU inference+upload)
- ✅ Forecasts land in MPC Pro blob storage
- ✅ Virtual Zarr references validated by MPC Pro team
- ✅ STAC catalog created and queryable
- ✅ End-to-end flow validated

---

## Milestone 3: Production & Scheduling

**Goal:** Automated 6h NRT operations with monitoring and reliability.
**Timeline:** ~1 week after M2.

### Steps

#### 3.1 — Enable 6h schedule
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
- **Depends on:** M2 complete

#### 3.2 — 24-hour burn-in
- Let 4 consecutive cycles run (00Z, 06Z, 12Z, 18Z)
- Verify:
  - All 4 runs complete successfully
  - Output appears in MPC Pro blob
  - STAC catalog updates for each run
  - No compute scaling issues
- **Depends on:** 3.1

#### 3.3 — Set up monitoring and alerts
- Configure Azure Monitor alerts:
  ```bash
  # Alert on pipeline failure
  az monitor metrics alert create \
    --name "eagle-pipeline-failure" \
    --resource <aml-workspace-resource-id> \
    --condition "count Failed Runs > 0" \
    --action-group <notify-team>
  ```
- Set up:
  - Pipeline failure notifications (email/Teams)
  - GPU OOM detection
  - Run duration anomaly (>2x normal = alert)
- **Depends on:** 3.1

#### 3.4 — Implement retry logic
- Add retry for data availability:
  ```python
  import time
  
  MAX_RETRIES = 3
  RETRY_DELAY = 600  # 10 minutes
  
  for attempt in range(MAX_RETRIES):
      try:
          load_initial_conditions(configs, version)
          break
      except DataNotAvailableError:
          if attempt < MAX_RETRIES - 1:
              time.sleep(RETRY_DELAY)
          else:
              raise
  ```
- **Depends on:** 3.1

#### 3.5 — Set storage lifecycle policy
```bash
az storage account management-policy create \
  --account-name <mpc-storage> \
  --policy '{
    "rules": [{
      "name": "nested-eagle-lifecycle",
      "type": "Lifecycle",
      "definition": {
        "filters": {"prefixMatch": ["nested-eagle-forecasts/"]},
        "actions": {
          "baseBlob": {
            "tierToCool": {"daysAfterModificationGreaterThan": 30},
            "delete": {"daysAfterModificationGreaterThan": 90}
          }
        }
      }
    }]
  }'
```
- Retention TBD (30/60/90 days — confirm with NOAA, Q5)
- **Depends on:** M2 complete

#### 3.6 — (Cost optimization) Evaluate spot compute
- For non-critical cycles, low-priority/spot GPU saves 60-80%:
  ```python
  gpu_cluster = AmlCompute(
      name="eagle-gpu-h100-spot",
      size="Standard_NC40ads_H100_v5",  # H100 80GB spot instance
      tier="low_priority",
      min_instances=0,
      max_instances=1,
  )
  ```
- Risk: spot VMs can be preempted. Acceptable if retry handles it.
- **Depends on:** 3.2 (burn-in confirms stability first)

#### 3.7 — Document runbook
- Write operations runbook covering:
  - How to manually trigger a run
  - How to investigate a failed run
  - How to update the checkpoint (new model version)
  - How to pause/resume the schedule
  - Contact list (NOAA, MPC Pro, Microsoft)
- **Depends on:** 3.2

### Milestone 3 Output
- ✅ Production schedule running every 6h
- ✅ Monitoring and failure alerts active
- ✅ Retry logic for data availability
- ✅ Storage lifecycle policy configured
- ✅ Operations runbook documented

---

## Milestone 4: Foundry & Optimization (Separate Scope)

**Goal:** Optional enhancements — separate from NRT pipeline delivery.

| Step | Task | Dependency |
|---|---|---|
| 4.1 | Evaluate listing in Azure AI Foundry model catalog | C7, NOAA approval |
| 4.2 | Prepare model card, documentation, evaluation benchmarks | 4.1 |
| 4.3 | Engage Foundry catalog team for onboarding | 4.2 |
| 4.4 | Switch HRRR/GFS source to Planetary Computer (if not done in M2) | C4 |
| 4.5 | Add Zarr output option (physical, not virtual) if needed | User demand |

**Note:** AML Model Registry (M1) is NOT the same as Foundry catalog. The registry is workspace-internal versioning — part of the standard pipeline. Foundry catalog is a public listing requiring a separate partnership engagement.

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

---

## Timeline Summary

| Milestone | Goal | Duration | Blocker |
|---|---|---|---|
| **M1** | Validate model on AML, confirm GPU | ~1-2 weeks | P1 (workspace), P2 (checkpoint), C1 (quota) |
| **M2** | Pipeline + MPC Pro integration | ~1-2 weeks | P3 (MPC storage) |
| **M3** | Production 6h schedule | ~1 week | M2 complete |
| **M4** | Foundry + optimization | TBD | Separate scope |
| **Total (M1-M3)** | **First public forecasts** | **~3-5 weeks from kickoff** | Prerequisites resolved |

---

## Cost Summary

| Scenario | GPU | Data Source | Monthly Cost |
|---|---|---|---|
| **Starting point** | H100 80GB | AWS | ~$350-840 |
| **After M1** (right-size GPU) | A10 24GB (if validated) | AWS | ~$80-130 |
| **After M2** (PC data + compression) | A10 24GB | PC (free) | ~$48-65 |
| **After M3** (lifecycle + spot) | A10 spot | PC (free) | ~$25-40 |
