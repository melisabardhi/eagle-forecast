"""
Step 8: Test inference on GPU cluster.

Submits a command job that runs inference.py on the GPU cluster.
This loads the checkpoint and initial conditions, runs 40 autoregressive
steps, and writes a 240h forecast as NetCDF.

Run this after test_preproc.py completes successfully.

Usage:
  python aml/test_inference.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from config import (
    get_ml_client,
    GPU_CLUSTER_NAME,
    ENVIRONMENT_NAME,
    MODEL_NAME,
    MODEL_VERSION,
)

from azure.ai.ml import command, Input


def main():
    ml_client = get_ml_client()
    print(f"Connected to workspace: {ml_client.workspace_name}\n")

    # Get the registered model path for the checkpoint
    model = ml_client.models.get(name=MODEL_NAME, version=MODEL_VERSION)
    print(f"Using model: {model.name} v{model.version}")

    print("Submitting inference test job to GPU cluster...")
    inference_job = command(
        code="./poc",
        command="python inference.py --config nested_eagle.yaml",
        environment=f"{ENVIRONMENT_NAME}:1",
        compute=GPU_CLUSTER_NAME,
        display_name="eagle-inference-test",
        experiment_name="nested-eagle-nrt",
        description="Test inference: load checkpoint, run 40 steps, write 240h forecast",
    )

    returned_job = ml_client.jobs.create_or_update(inference_job)

    print(f"  Job name:   {returned_job.name}")
    print(f"  Status:     {returned_job.status}")
    print(f"  Studio URL: {returned_job.studio_url}")
    print()
    print("Monitor the job in the AML Studio URL above.")
    print("Check GPU metrics in the Monitoring tab for peak VRAM usage.")
    print()
    print("Once it completes:")
    print("  - If peak VRAM < 20GB: consider switching to A10 24GB")
    print("  - If peak VRAM 20-70GB: consider switching to A100 80GB")
    print("  - Then run: python aml/pipeline.py")


if __name__ == "__main__":
    main()
