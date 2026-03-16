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

# Compute cluster names
CPU_CLUSTER_NAME = "eagle-cpu"
GPU_CLUSTER_NAME = "eagle-gpu"

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
