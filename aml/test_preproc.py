"""
Step 7: Test preprocessing on CPU cluster.

Submits a command job that runs preproc.py on the CPU cluster.
This downloads GFS + HRRR initial conditions and regrids HRRR to 6km.

Usage:
  python aml/test_preproc.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from config import (
    get_ml_client,
    CPU_CLUSTER_NAME,
    ENVIRONMENT_NAME,
)

from azure.ai.ml import command, Input


def main():
    ml_client = get_ml_client()
    print(f"Connected to workspace: {ml_client.workspace_name}\n")

    print("Submitting preprocessing test job to CPU cluster...")
    preproc_job = command(
        code="./poc",
        command="python preproc.py --config nested_eagle.yaml",
        environment=f"{ENVIRONMENT_NAME}:1",
        compute=CPU_CLUSTER_NAME,
        display_name="eagle-preproc-test",
        experiment_name="nested-eagle-nrt",
        description="Test preprocessing: download GFS + HRRR, regrid HRRR to 6km",
    )

    returned_job = ml_client.jobs.create_or_update(preproc_job)

    print(f"  Job name:   {returned_job.name}")
    print(f"  Status:     {returned_job.status}")
    print(f"  Studio URL: {returned_job.studio_url}")
    print()
    print("Monitor the job in the AML Studio URL above.")
    print("Once it completes, run: python aml/test_inference.py")


if __name__ == "__main__":
    main()
