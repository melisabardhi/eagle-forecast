"""
Azure Function to scale up Azure ML compute cluster minimum nodes.

This function is triggered on a schedule to increase the minimum nodes
from 0 to 1 for specified Azure ML compute clusters. This ensures
clusters are pre-warmed and ready for immediate job execution.
"""

import logging
import os
from typing import Optional

import azure.functions as func
from azure.ai.ml import MLClient
from azure.ai.ml.entities import AmlCompute
from azure.identity import DefaultAzureCredential


# Configuration - these should be set as Application Settings in Azure
SUBSCRIPTION_ID = os.environ.get("AZURE_SUBSCRIPTION_ID", "")
RESOURCE_GROUP = os.environ.get("AZURE_RESOURCE_GROUP", "")
WORKSPACE_NAME = os.environ.get("AZURE_ML_WORKSPACE_NAME", "")

# Cluster configuration (comma-separated list)
CLUSTERS_TO_SCALE = os.environ.get("CLUSTERS_TO_SCALE", "eagle-cpu,eagle-gpu-h100")
SCALE_UP_CRON = os.environ.get("SCALE_UP_CRON", "0 0 8 * * 1-5")  # Default: 8 AM UTC, weekdays
SCALE_DOWN_CRON = os.environ.get("SCALE_DOWN_CRON", "")  # Optional scale down


def get_clusters_list() -> list:
    """Parse clusters list from environment variable."""
    return [cluster.strip() for cluster in CLUSTERS_TO_SCALE.split(',') if cluster.strip()]

app = func.FunctionApp()


def get_ml_client() -> MLClient:
    """Create and return an authenticated MLClient."""
    credential = DefaultAzureCredential()
    return MLClient(
        credential=credential,
        subscription_id=SUBSCRIPTION_ID,
        resource_group_name=RESOURCE_GROUP,
        workspace_name=WORKSPACE_NAME,
    )


def scale_cluster_min_nodes(ml_client: MLClient, cluster_name: str, min_nodes: int = 1) -> bool:
    """
    Scale the minimum nodes of a compute cluster.
    
    Args:
        ml_client: Authenticated Azure ML client
        cluster_name: Name of the compute cluster to scale
        min_nodes: Target minimum number of nodes (default: 1)
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Get current cluster configuration
        cluster = ml_client.compute.get(cluster_name)
        
        if not isinstance(cluster, AmlCompute):
            logging.error(f"Cluster {cluster_name} is not an AmlCompute cluster")
            return False
        
        current_min = cluster.min_instances
        logging.info(f"Current min_instances for {cluster_name}: {current_min}")
        
        if current_min >= min_nodes:
            logging.info(f"Cluster {cluster_name} already has min_instances >= {min_nodes}, no action needed")
            return True
        
        # Update cluster configuration
        cluster.min_instances = min_nodes
        
        # Apply the update
        logging.info(f"Updating {cluster_name} min_instances from {current_min} to {min_nodes}...")
        ml_client.compute.begin_create_or_update(cluster).result()
        
        logging.info(f"Successfully updated {cluster_name} min_instances to {min_nodes}")
        return True
        
    except Exception as e:
        logging.error(f"Failed to update cluster {cluster_name}: {str(e)}")
        return False


@app.timer_trigger(
    schedule="0 0 8 * * 1-5",  # 8 AM UTC, Monday-Friday (adjust as needed)
    arg_name="mytimer",
    run_on_startup=False,
    use_monitor=False
)
def scale_up_clusters(mytimer: func.TimerRequest) -> None:
    """
    Timer-triggered function to scale up Azure ML compute clusters.
    
    Schedule format: "0 0 8 * * 1-5" means:
    - 0 seconds
    - 0 minutes  
    - 8 hours (8 AM)
    - Any day of month
    - Any month
    - Monday-Friday (1-5)
    
    Modify the schedule as needed for your use case.
    """
    logging.info("Scale-up function starting...")
    
    # Validate environment variables
    if not all([SUBSCRIPTION_ID, RESOURCE_GROUP, WORKSPACE_NAME]):
        logging.error("Missing required environment variables")
        logging.error(f"AZURE_SUBSCRIPTION_ID: {'✓' if SUBSCRIPTION_ID else '✗'}")
        logging.error(f"AZURE_RESOURCE_GROUP: {'✓' if RESOURCE_GROUP else '✗'}")
        logging.error(f"AZURE_ML_WORKSPACE_NAME: {'✓' if WORKSPACE_NAME else '✗'}")
        return
    
    try:
        # Get authenticated ML client
        ml_client = get_ml_client()
        logging.info("Successfully authenticated with Azure ML")
        
        # Get clusters to scale from configuration
        clusters_to_scale = get_clusters_list()
        
        success_count = 0
        for cluster_name in clusters_to_scale:
            if cluster_name:  # Only process if cluster name is not empty
                logging.info(f"Processing cluster: {cluster_name}")
                if scale_cluster_min_nodes(ml_client, cluster_name, min_nodes=1):
                    success_count += 1
                else:
                    logging.warning(f"Failed to scale cluster: {cluster_name}")
        
        logging.info(f"Scale-up completed. Successfully updated {success_count}/{len(clusters_to_scale)} clusters")
        
    except Exception as e:
        logging.error(f"Scale-up function failed with error: {str(e)}")


@app.timer_trigger(
    schedule="0 0 18 * * 1-5",  # 6 PM UTC, Monday-Friday (optional scale-down)
    arg_name="mytimer", 
    run_on_startup=False,
    use_monitor=False
)
def scale_down_clusters(mytimer: func.TimerRequest) -> None:
    """
    Optional timer-triggered function to scale down clusters after hours.
    
    This function scales clusters back to min_instances=0 to save costs.
    Remove or disable this trigger if you want clusters to stay scaled up.
    """
    logging.info("Scale-down function starting...")
    
    # Validate environment variables
    if not all([SUBSCRIPTION_ID, RESOURCE_GROUP, WORKSPACE_NAME]):
        logging.error("Missing required environment variables")
        return
    
    try:
        # Get authenticated ML client
        ml_client = get_ml_client()
        logging.info("Successfully authenticated with Azure ML")
        
        # Get clusters to scale from configuration
        clusters_to_scale = get_clusters_list()
        
        success_count = 0
        for cluster_name in clusters_to_scale:
            if cluster_name:  # Only process if cluster name is not empty
                logging.info(f"Scaling down cluster: {cluster_name}")
                if scale_cluster_min_nodes(ml_client, cluster_name, min_nodes=0):
                    success_count += 1
                else:
                    logging.warning(f"Failed to scale down cluster: {cluster_name}")
        
        logging.info(f"Scale-down completed. Successfully updated {success_count}/{len(clusters_to_scale)} clusters")
        
    except Exception as e:
        logging.error(f"Scale-down function failed with error: {str(e)}")