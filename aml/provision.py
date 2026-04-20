"""
Step 3 + 5 + 6: Provision AML resources.

Run this after:
  - Filling in aml/config.py with your workspace details
  - Verifying GPU quota (Step 1)
  - Creating output blob container (Step 2)

This script will:
  1. Create a datastore for the checkpoint storage
  2. Register the checkpoint as an AML model
  3. Provision CPU compute cluster (scale-to-zero)
  4. Provision GPU compute cluster (scale-to-zero)
  5. Register the Docker+conda environment

Usage:
  python aml/provision.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from config import (
    get_ml_client,
    CHECKPOINT_STORAGE_ACCOUNT,
    CHECKPOINT_CONTAINER,
    CHECKPOINT_PATH,
    CPU_CLUSTER_NAME,
    GPU_CLUSTER_NAME,
    ENVIRONMENT_NAME,
    MODEL_NAME,
    MODEL_VERSION,
)

from azure.ai.ml.entities import (
    AmlCompute,
    Environment,
    Model,
    AzureBlobDatastore,
)


def create_checkpoint_datastore(ml_client):
    """Create a datastore pointing to the checkpoint blob storage."""
    print("Creating datastore 'eagle-checkpoints'...")
    datastore = AzureBlobDatastore(
        name="eagle-checkpoints",
        account_name=CHECKPOINT_STORAGE_ACCOUNT,
        container_name=CHECKPOINT_CONTAINER,
        description="Nested-EAGLE model checkpoints",
    )
    ml_client.datastores.create_or_update(datastore)
    print("  Done.")


def register_model(ml_client):
    """Register the checkpoint as an AML model."""
    print(f"Registering model '{MODEL_NAME}' version {MODEL_VERSION}...")
    model = Model(
        name=MODEL_NAME,
        version=MODEL_VERSION,
        path=f"azureml://datastores/eagle-checkpoints/paths/{CHECKPOINT_PATH}/inference-last.ckpt",
        type="custom_model",
        description="Nested-EAGLE NRT weather forecast model (Anemoi framework)",
        tags={
            "framework": "anemoi-inference",
            "grid": "nested-cutout-6km",
            "lead_time": "240h",
            "version": "nested_eagle",
        },
    )
    ml_client.models.create_or_update(model)
    print("  Done.")


def provision_cpu_cluster(ml_client):
    """Provision CPU compute cluster for preprocessing (scale-to-zero)."""
    print(f"Provisioning CPU cluster '{CPU_CLUSTER_NAME}'...")
    cpu_cluster = AmlCompute(
        name=CPU_CLUSTER_NAME,
        type="amlcompute",
        size="Standard_D16s_v5",
        min_instances=0,
        max_instances=1,
        idle_time_before_scale_down=300,
    )
    ml_client.compute.begin_create_or_update(cpu_cluster).result()
    print("  Done.")


def provision_gpu_cluster(ml_client):
    """Provision GPU compute cluster for inference (scale-to-zero)."""
    print(f"Provisioning GPU cluster '{GPU_CLUSTER_NAME}'...")
    gpu_cluster = AmlCompute(
        name=GPU_CLUSTER_NAME,
        type="amlcompute",
        size="Standard_NC40ads_H100_v5",
        min_instances=0,
        max_instances=1,
        idle_time_before_scale_down=300,
    )
    ml_client.compute.begin_create_or_update(gpu_cluster).result()
    print("  Done.")


def register_environment(ml_client):
    """Register the Docker + conda environment."""
    print(f"Registering environment '{ENVIRONMENT_NAME}'...")
    env_path = os.path.join(os.path.dirname(__file__), "environment")
    env = Environment(
        name=ENVIRONMENT_NAME,
        build={"path": env_path},
        description="Nested-EAGLE NRT: anemoi-inference, torch, flash-attn, ufs2arco",
    )
    ml_client.environments.create_or_update(env)
    print("  Done. (Docker image builds on first job submission.)")


def main():
    ml_client = get_ml_client()
    print(f"Connected to workspace: {ml_client.workspace_name}\n")

    create_checkpoint_datastore(ml_client)
    register_model(ml_client)
    provision_cpu_cluster(ml_client)
    provision_gpu_cluster(ml_client)
    register_environment(ml_client)

    print("\nAll resources provisioned. Next steps:")
    print("  1. Generate hrrr_06km.nc: python poc/config/hrrr_6km.py")
    print("  2. Test preprocessing:    python aml/test_preproc.py")
    print("  3. Test inference:        python aml/test_inference.py")


if __name__ == "__main__":
    main()
