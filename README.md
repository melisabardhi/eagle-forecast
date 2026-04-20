# Nested-EAGLE

Near-real-time (NRT) AI weather forecasting pipeline and Azure AI Foundry model registration for the Nested-EAGLE model — a NOAA/EPIC AI weather model built on the [ECMWF Anemoi framework](https://anemoi-docs.readthedocs.io/).

Nested-EAGLE produces 240-hour (10-day) forecasts every 6 hours by nesting a high-resolution HRRR grid (6 km, CONUS) inside a global GFS grid (0.25°), running on a single H100 80GB GPU.

---

## Repository structure

```
├── poc/                        # Inference + post-processing + GeoCatalog pipeline
│   ├── inference.py            # Run eagle_inference() + post-process + upload
│   ├── preproc.py              # Download and regrid GFS/HRRR initial conditions
│   ├── postproc.py             # Split raw forecast → global.nc + conus.nc
│   ├── upload.py               # Upload NetCDF + STAC to Azure Blob Storage
│   ├── ingest.py               # Ingest STAC items into MPC Pro GeoCatalog
│   ├── stac_item.py            # Generate STAC Item JSONs
│   ├── stac_collection.json    # STAC Collection definition
│   └── nested_eagle.yaml       # Config file (checkpoint path, storage, GeoCatalog)
│
├── aml/                        # Azure ML deployment scripts
│   ├── README.md               # Step-by-step AML deployment guide
│   ├── config.py               # Shared workspace + storage configuration
│   ├── provision.py            # Provision compute, register model + environment
│   ├── pipeline.py             # Build 2-step AML pipeline + 6h schedule
│   ├── test_preproc.py         # Submit CPU preprocessing test job
│   ├── test_inference.py       # Submit GPU inference test job
│   ├── setup_client.py         # Verify AML SDK connection
│   ├── environment/            # Docker + conda environment definition
│   └── scripts/
│       ├── apim/               # GeoCatalog APIM proxy setup
│       └── scaling/            # Azure Function for scheduled cluster scaling
│
├── byoc/                       # BYOC container for Azure AI Foundry deployment
│   ├── score.py                # AML managed online endpoint scoring script
│   ├── Dockerfile              # Container image (CUDA 12.1 + anemoi-inference)
│   ├── conda.yaml              # Python dependencies
│   └── README.md               # Build, push, and deploy instructions
│
├── foundry_registration/       # Azure AI Foundry model card files
│   ├── description.md          # Model description
│   ├── evaluation.md           # Benchmark evaluation table
│   ├── notes.md                # Intended use, RAI, training data
│   └── required_metadata.md    # 19 required Foundry metadata fields
│
├── arch.md                     # System architecture + data flow diagrams
├── deployment.md               # End-to-end deployment guide
└── docs.md                     # Full technical documentation
```

---

## What this repo covers

### 1. NRT operational pipeline (`aml/` + `poc/`)
Runs every 6 hours on Azure ML. Preprocessing on CPU → inference on H100 → post-processing → upload to MPC Pro GeoCatalog for public distribution via Planetary Computer.

See [`aml/README.md`](aml/README.md) for the full deployment guide.

### 2. Azure AI Foundry model registration (`foundry_registration/` + `byoc/`)
Registers Nested-EAGLE in the Azure AI Foundry model catalog (non-IPP, Apache 2.0). Users can deploy the BYOC container to their own Azure subscription and run on-demand inference.

See [`byoc/README.md`](byoc/README.md) for the container deployment guide.

---

## Quickstart (NRT pipeline)

```bash
# 1. Configure workspace + storage
cp poc/nested_eagle.yaml poc/my_config.yaml
# Edit: checkpoint_path, output_storage_account, geocat_url

# 2. Edit aml/config.py with your workspace details

# 3. Provision AML resources (compute, model, environment)
python aml/provision.py

# 4. Test preprocessing
python aml/test_preproc.py

# 5. Test inference
python aml/test_inference.py

# 6. Enable 6h schedule
python aml/pipeline.py --schedule
```

## Quickstart (Foundry BYOC endpoint)

See [`byoc/README.md`](byoc/README.md).

---

## Requirements

- Azure subscription with AML workspace
- GPU quota: `Standard_NC40ads_H100_v5` (H100 80GB, 40 cores)
- Model checkpoint: `inference-last.ckpt` (contact NOAA/EPIC)
- Static grid file: `hrrr_06km.nc` (generate with `poc/config/hrrr_6km.py`)

---

## License

Model weights: [Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0) (ECMWF Anemoi framework)  
Code in this repository: Apache 2.0

## Acknowledgements

Developed by NOAA/EPIC with support from Microsoft. Built on the [ECMWF Anemoi framework](https://anemoi-docs.readthedocs.io/).

