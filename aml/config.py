"""
Shared AML configuration for all Nested-EAGLE deployment scripts.

Update the values below with your workspace details, then all scripts
(provision.py, test_preproc.py, test_inference.py, pipeline.py) will
use the same connection.
"""

from azure.ai.ml import MLClient
from azure.identity import DefaultAzureCredential

# --- FILL IN WITH YOUR WORKSPACE DETAILS ---
SUBSCRIPTION_ID = "<SUBSCRIPTION_ID>"
RESOURCE_GROUP = "<RESOURCE_GROUP>"
WORKSPACE_NAME = "<WORKSPACE_NAME>"

# Checkpoint storage
CHECKPOINT_STORAGE_ACCOUNT = "eaglecheckpoints"
CHECKPOINT_CONTAINER = "eagle-checkpoints"
CHECKPOINT_PATH = "poc"

# Output storage (created in Step 2)
OUTPUT_STORAGE_ACCOUNT = "<FORECAST_STORAGE_ACCOUNT>"
OUTPUT_CONTAINER = "nested-eagle-forecasts"
OUTPUT_STORAGE_URL = f"https://{OUTPUT_STORAGE_ACCOUNT}.blob.core.windows.net/{OUTPUT_CONTAINER}"

# Data retention: 90 days during experimental phase (no PC access).
# Once data flows to Planetary Computer, reduce to 7 days.
DATA_RETENTION_DAYS = 90

# GeoCatalog (MPC Pro) — for public distribution via Planetary Computer
# Fill in after creating the GeoCatalog instance in the NOAA subscription.
# Leave empty to skip ingestion (Track 1 only, internal evaluation).
GEOCATALOG_URL = "<GEOCATALOG_URL>"  # e.g. https://<name>.<id>.<region>.geocatalog.spatio.azure.com
GEOCATALOG_COLLECTION_ID = "noaa-nested-eagle"

# Compute cluster names
CPU_CLUSTER_NAME = "eagle-cpu"
GPU_CLUSTER_NAME = "eagle-gpu-h100"

# Environment name
ENVIRONMENT_NAME = "eagle-nrt"

# Model name
MODEL_NAME = "nested-eagle"
MODEL_VERSION = "1"


def get_ml_client() -> MLClient:
    """Create and return an authenticated MLClient."""
    credential = DefaultAzureCredential()
    return MLClient(
        credential=credential,
        subscription_id=SUBSCRIPTION_ID,
        resource_group_name=RESOURCE_GROUP,
        workspace_name=WORKSPACE_NAME,
    )
