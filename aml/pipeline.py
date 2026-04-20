"""
Steps 9 + 10: Build the 2-step AML pipeline and enable the 6h schedule.

This script:
  1. Defines a 2-step pipeline:
     - Step 1 (CPU): preprocessing — download GFS/HRRR, regrid, write Zarr
     - Step 2 (GPU): inference + upload — run forecast, write NetCDF, upload to blob
  2. Submits a test pipeline run
  3. Optionally creates a 6h recurring schedule

Run this after test_preproc.py and test_inference.py both complete successfully.

Usage:
  python aml/pipeline.py              # Submit a single test run
  python aml/pipeline.py --schedule   # Create the 6h recurring schedule
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from config import (
    get_ml_client,
    CPU_CLUSTER_NAME,
    GPU_CLUSTER_NAME,
    ENVIRONMENT_NAME,
    OUTPUT_STORAGE_ACCOUNT,
    OUTPUT_CONTAINER,
    OUTPUT_STORAGE_URL,
)

from azure.ai.ml import command, dsl, Input, Output
from azure.ai.ml.entities import RecurrenceTrigger, JobSchedule


@dsl.pipeline(
    name="nested-eagle-nrt",
    description="Nested-EAGLE NRT: 6h weather forecast pipeline",
)
def nested_eagle_pipeline():
    """2-step pipeline: CPU preprocessing → GPU inference + upload."""

    # Step 1: Preprocessing (CPU)
    # Downloads GFS + HRRR, regrids HRRR to 6km, writes Zarr
    preproc_step = command(
        code="./poc",
        command="python preproc.py --config nested_eagle.yaml --version ${{outputs.preproc_output}}",
        outputs={"preproc_output": Output(type="uri_folder")},
        environment=f"{ENVIRONMENT_NAME}:1",
        compute=CPU_CLUSTER_NAME,
        display_name="preproc",
        description="Download GFS + HRRR, regrid HRRR to 6km, write Zarr",
    )

    # Step 2: Inference + Upload + STAC (GPU)
    # Loads checkpoint, runs forecast, writes NetCDF, generates STAC Item, uploads to blob
    # Must wait for preprocessing to finish
    inference_step = command(
        code="./poc",
        command=(
            "python inference.py --config nested_eagle.yaml --version ${{inputs.preproc_output}} --output_path ${{outputs.forecast_results}} --checkpoint_path ${{inputs.model_checkpoint}}"
        ),
        inputs={
            "preproc_output": Input(type="uri_folder"), 
            "model_checkpoint": Input(type="custom_model")
        },
        outputs={"forecast_results": Output(type="uri_folder")},
        environment=f"{ENVIRONMENT_NAME}:1",
        compute=GPU_CLUSTER_NAME,
        display_name="inference-and-upload",
        description="Run 240h forecast, write NetCDF, generate STAC Item, upload all to output blob",
    )
    inference_step.inputs.preproc_output = preproc_step.outputs.preproc_output
    inference_step.after(preproc_step)

    return {}


def submit_test_run(ml_client):
    """Submit a single test pipeline run."""
    print("Submitting test pipeline run...")
    pipeline_job = ml_client.jobs.create_or_update(
        nested_eagle_pipeline(),
        experiment_name="nested-eagle-nrt",
    )
    print(f"  Job name:   {pipeline_job.name}")
    print(f"  Status:     {pipeline_job.status}")
    print(f"  Studio URL: {pipeline_job.studio_url}")
    print()
    print("Monitor the pipeline in the AML Studio URL above.")
    print("Once validated, enable the schedule with: python aml/pipeline.py --schedule")


def create_schedule(ml_client):
    """Create a 6h recurring schedule for the pipeline."""
    print("Creating 6h recurring schedule...")

    schedule = JobSchedule(
        name="nested-eagle-6h",
        trigger=RecurrenceTrigger(
            frequency="hour",
            interval=6,
            start_time="2026-04-01T00:00:00Z",
            time_zone="UTC",
        ),
        create_job=nested_eagle_pipeline(),
    )

    returned_schedule = ml_client.schedules.begin_create_or_update(schedule).result()
    print(f"  Schedule name:   {returned_schedule.name}")
    print(f"  Trigger:         Every 6 hours (00Z, 06Z, 12Z, 18Z)")
    print(f"  Status:          {returned_schedule.is_enabled}")
    print()
    print("Schedule is active. The pipeline will run every 6 hours.")
    print()
    print("To disable the schedule:")
    print("  ml_client.schedules.begin_disable('nested-eagle-6h')")
    print()
    print("To check schedule status:")
    print("  ml_client.schedules.get('nested-eagle-6h')")


def main():
    parser = argparse.ArgumentParser(description="Nested-EAGLE AML Pipeline")
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Create the 6h recurring schedule (instead of a single test run)",
    )
    parser.add_argument(
        "--checkpoint_path",
        type=str,
        default="azureml://models/nested-eagle-model/versions/1",
        help="Path to the registered model checkpoint (default: azureml://models/nested-eagle-model/versions/1)",
    )
    args = parser.parse_args()

    ml_client = get_ml_client()
    print(f"Connected to workspace: {ml_client.workspace_name}\n")

    if args.schedule:
        create_schedule(ml_client)
    else:
        submit_test_run(ml_client)


if __name__ == "__main__":
    main()
