"""
Component-based version of the pipeline using @command_component decorators.

This follows the official Azure ML documentation pattern for pipelines.
"""

import argparse
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from config import (
    get_ml_client,
    CPU_CLUSTER_NAME,
    GPU_CLUSTER_NAME,
    ENVIRONMENT_NAME,
    OUTPUT_STORAGE_ACCOUNT,
    OUTPUT_CONTAINER,
)

from azure.ai.ml import dsl, Input, Output
from azure.ai.ml.entities import RecurrenceTrigger, JobSchedule
from mldesigner import command_component


# Component 1: Preprocessing
@command_component(
    name="nested_eagle_preproc",
    version="1",
    display_name="Nested-EAGLE Preprocessing",
    description="Download GFS + HRRR, regrid HRRR to 6km, write Zarr",
    environment=dict(
        image="mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu20.04",
        # Note: In practice, you'd reference your actual environment
        # environment=f"{ENVIRONMENT_NAME}:1"
    ),
)
def preproc_component(
    preproc_output: Output(type="uri_folder")
):
    """
    Preprocessing component that downloads and processes weather data.
    
    Args:
        preproc_output: Output directory for processed Zarr files
    """
    import subprocess
    import os
    
    # The actual preprocessing logic
    cmd = [
        "python", "preproc.py", 
        "--config", "nested_eagle.yaml",
        "--version", str(preproc_output)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, cwd="./poc")
    if result.returncode != 0:
        raise RuntimeError(f"Preprocessing failed: {result.stderr}")


# Component 2: Inference
@command_component(
    name="nested_eagle_inference",
    version="1", 
    display_name="Nested-EAGLE Inference",
    description="Run 240h forecast, write NetCDF, upload to output blob",
    environment=dict(
        image="mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu20.04",
        # Note: In practice, you'd reference your actual environment
        # environment=f"{ENVIRONMENT_NAME}:1"
    ),
)
def inference_component(
    preproc_output: Input(type="uri_folder"),
    forecast_results: Output(type="uri_folder")
):
    """
    Inference component that runs weather forecast model.
    
    Args:
        preproc_output: Input directory with preprocessed Zarr files
        forecast_results: Output directory for forecast NetCDF files
    """
    import subprocess
    
    # The actual inference logic
    cmd = [
        "python", "inference.py",
        "--config", "nested_eagle.yaml", 
        "--version", str(preproc_output),
        "--output_path", str(forecast_results)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, cwd="./poc")  
    if result.returncode != 0:
        raise RuntimeError(f"Inference failed: {result.stderr}")


# Component 3: Post-processing & Upload
@command_component(
    name="nested_eagle_postproc",
    version="1",
    display_name="Nested-EAGLE Post-processing & STAC Upload",
    description="Split forecast into global/CONUS files, generate STAC items, upload to blob",
    environment=dict(
        image="mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu20.04",
        # Note: In practice, you'd reference your actual environment
        # environment=f"{ENVIRONMENT_NAME}:1"
    ),
)
def postproc_component(
    forecast_results: Input(type="uri_folder"),
    final_outputs: Output(type="uri_folder")
):
    """
    Post-processing component that splits forecast data and creates STAC items.
    
    Args:
        forecast_results: Input directory with raw forecast NetCDF files
        final_outputs: Output directory for processed files and STAC metadata
    """
    import subprocess
    import shutil
    import os
    
    # Step 1: Post-process raw forecast (split into global.nc and conus.nc)
    postproc_cmd = [
        "python", "postproc.py",
        "--config", "nested_eagle.yaml",
        "--input_path", str(forecast_results),
        "--output_path", str(final_outputs)
    ]
    
    result = subprocess.run(postproc_cmd, capture_output=True, text=True, cwd="./poc")
    if result.returncode != 0:
        raise RuntimeError(f"Post-processing failed: {result.stderr}")
    
    # Step 3: Upload to blob storage (data files must exist before STAC ingestion)
    upload_cmd = [
        "python", "upload.py", 
        "--config", "nested_eagle.yaml",
        "--input_path", str(final_outputs),
        "--storage_account", OUTPUT_STORAGE_ACCOUNT,
        "--container", OUTPUT_CONTAINER
    ]
    
    result = subprocess.run(upload_cmd, capture_output=True, text=True, cwd="./poc")
    if result.returncode != 0:
        raise RuntimeError(f"Upload failed: {result.stderr}")
    
    # Step 4: Generate STAC items and ingest into GeoCatalog (references uploaded URLs)
    # Note: Add geocatalog_url to your nested_eagle.yaml config file
    stac_cmd = [
        "python", "stac_ingestion.py",
        "--config", "nested_eagle.yaml",
        "--geocatalog-url", "https://your-geocatalog.com"  # TODO: Configure this
    ]
    
    result = subprocess.run(stac_cmd, capture_output=True, text=True, cwd="./poc")
    if result.returncode != 0:
        raise RuntimeError(f"STAC ingestion failed: {result.stderr}")


# Pipeline definition using components
@dsl.pipeline(
    name="nested-eagle-nrt-components",
    description="Nested-EAGLE NRT: Complete 6h weather forecast pipeline (component-based)",
)
def nested_eagle_pipeline_components():
    """3-step pipeline using components: CPU preprocessing → GPU inference → CPU post-processing + STAC + upload."""

    # Step 1: Preprocessing (CPU) - returns component instance
    preproc_step = preproc_component()
    preproc_step.compute = CPU_CLUSTER_NAME
    
    # Step 2: Inference (GPU) - pass preproc output as input
    inference_step = inference_component(
        preproc_output=preproc_step.outputs.preproc_output
    )
    inference_step.compute = GPU_CLUSTER_NAME
    
    # Step 3: Post-processing + Upload (CPU) - pass inference output as input
    postproc_step = postproc_component(
        forecast_results=inference_step.outputs.forecast_results
    )
    postproc_step.compute = CPU_CLUSTER_NAME
    
    # Return pipeline outputs (optional)
    return {
        "final_outputs": postproc_step.outputs.final_outputs
    }


def submit_test_run(ml_client):
    """Submit a single test pipeline run."""
    print("Submitting complete 3-step component-based test pipeline run...")
    pipeline_job = ml_client.jobs.create_or_update(
        nested_eagle_pipeline_components(),
        experiment_name="nested-eagle-nrt-components",
    )
    print(f"  Job name:   {pipeline_job.name}")
    print(f"  Status:     {pipeline_job.status}")
    print(f"  Studio URL: {pipeline_job.studio_url}")
    print()
    print("Monitor the pipeline in the AML Studio URL above.")


def create_schedule(ml_client):
    """Create a 6h recurring schedule for the component-based pipeline."""
    print("Creating 6h recurring schedule for complete component-based pipeline...")

    schedule = JobSchedule(
        name="nested-eagle-components-6h",
        trigger=RecurrenceTrigger(
            frequency="hour",
            interval=6,
            start_time="2026-04-01T00:00:00Z",
        ),
        create_job=nested_eagle_pipeline_components(),
        display_name="Nested-EAGLE Complete Component Pipeline - 6h",
        description="Complete 3-step component-based 6h recurring weather forecast pipeline with STAC upload",
    )

    created_schedule = ml_client.schedules.begin_create_or_update(schedule).result()
    print(f"  Schedule name: {created_schedule.name}")
    print(f"  Status:        {created_schedule.provisioning_state}")
    print(f"  Trigger:       Every 6 hours")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--schedule", 
        action="store_true", 
        help="Create recurring 6h schedule"
    )
    args = parser.parse_args()

    # Get ML client
    ml_client = get_ml_client()

    if args.schedule:
        create_schedule(ml_client)
    else:
        submit_test_run(ml_client)