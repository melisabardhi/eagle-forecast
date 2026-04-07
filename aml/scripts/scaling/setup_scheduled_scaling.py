#!/usr/bin/env python3
"""
Azure Function deployment for ML cluster scheduled auto-scaling.

Usage:
    # From CLI with arguments (recommended)
    python aml/scripts/scaling/setup_scheduled_scaling.py \
      --subscription-id <sub-id> \
      --ml-resource-group <ml-rg> \
      --ml-workspace <workspace>
    
    # Or use existing aml/config.py (if configured)
    python aml/scripts/scaling/setup_scheduled_scaling.py

Prerequisites:
    1. Azure CLI: az login
    2. Azure ML workspace and compute clusters already exist
"""

import argparse
import json
import os
import sys
import subprocess
import time
import uuid
import zipfile
from pathlib import Path
from typing import Dict, Any, Optional

# Make YAML support optional
try:
    import yaml
    HAS_YAML_SUPPORT = True
except ImportError:
    yaml = None
    HAS_YAML_SUPPORT = False


def load_yaml_config(config_path: str) -> dict:
    """Load configuration from YAML file."""
    if not HAS_YAML_SUPPORT:
        print("❌ YAML support not available. Install PyYAML to use config files:")
        print("   pip install pyyaml>=6.0")
        print("   or use command line arguments instead")
        sys.exit(1)
        
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        if not isinstance(config, dict):
            raise ValueError("YAML configuration must be a dictionary")
            
        return config
    except FileNotFoundError:
        print(f"❌ Configuration file not found: {config_path}")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"❌ Invalid YAML configuration: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error loading configuration: {e}")
        sys.exit(1)


def merge_config_with_args(yaml_config: dict, args: argparse.Namespace) -> dict:
    """Merge YAML configuration with command line arguments.
    
    Command line arguments take precedence over YAML values.
    """
    # Convert argparse Namespace to dict
    cli_config = {k: v for k, v in vars(args).items() if v is not None}
    
    # Merge configs (CLI args override YAML)
    merged = yaml_config.copy()
    merged.update(cli_config)
    
    # Handle special cases where YAML uses different formats
    if 'clusters' in yaml_config and isinstance(yaml_config['clusters'], list):
        # YAML can have clusters as a list, convert to comma-separated string
        if 'clusters' not in cli_config:  # Only if not overridden by CLI
            merged['clusters'] = ','.join(yaml_config['clusters'])
    
    return merged


def get_current_subscription_id() -> Optional[str]:
    """Get the current subscription ID from Azure CLI context."""
    try:
        result = subprocess.run(['az', 'account', 'show', '--query', 'id', '-o', 'tsv'], 
                              capture_output=True, text=True, check=True)
        subscription_id = result.stdout.strip()
        if subscription_id:
            return subscription_id
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return None


def validate_merged_config(config: dict) -> None:
    """Validate that all required configuration is present."""
    # Check required fields using the CLI argument names (with hyphens)
    required_cli_args = ['ml-resource-group', 'ml-workspace']
    
    # Try to automatically get subscription ID if not provided
    if not config.get('subscription_id') and not config.get('subscription-id'):
        subscription_id = get_current_subscription_id()
        if subscription_id:
            config['subscription-id'] = subscription_id
            print(f"✅ Using current subscription: {subscription_id}")
        else:
            print("⚠️  Could not automatically detect subscription. Make sure you're logged in with 'az login'")
    
    # Check for missing required arguments
    missing = []
    for field in required_cli_args:
        # Check both hyphenated and underscored versions
        field_underscore = field.replace('-', '_')
        has_hyphen_version = config.get(field) is not None
        has_underscore_version = config.get(field_underscore) is not None
        
        if not has_hyphen_version and not has_underscore_version:
            missing.append(field)
    
    if missing:
        print("❌ Missing required configuration:")
        for field in missing:
            print(f"   - {field} (CLI: --{field}, YAML: {field})")
        print("\n💡 Provide missing values via command line arguments or YAML configuration file")
        sys.exit(1)


def get_current_subscription() -> Optional[str]:
    """Get current Azure CLI subscription ID."""
    try:
        result = subprocess.run(
            ["az", "account", "show", "--query", "id", "-o", "tsv"], 
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def load_config_or_prompt() -> tuple[str, str, str]:
    """Load config from aml/config.py or prompt user for values."""
    
    # Try to load from config.py first
    try:
        # Add the aml directory to Python path to import config
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from config import SUBSCRIPTION_ID, RESOURCE_GROUP, WORKSPACE_NAME
        
        # Check if values are properly configured
        if (SUBSCRIPTION_ID and SUBSCRIPTION_ID != "<SUBSCRIPTION_ID>" and
            RESOURCE_GROUP and RESOURCE_GROUP != "<RESOURCE_GROUP>" and
            WORKSPACE_NAME and WORKSPACE_NAME != "<WORKSPACE_NAME>"):
            print("✅ Using configuration from aml/config.py")
            return SUBSCRIPTION_ID, RESOURCE_GROUP, WORKSPACE_NAME
    except ImportError:
        pass
    except Exception as e:
        print(f"⚠️  Could not load aml/config.py: {e}")
    
    # No valid config found, prompt user
    print("❌ No valid configuration found in aml/config.py")
    print("💡 Please provide Azure ML workspace details via command line arguments:")
    print("   --subscription-id <your-subscription-id>")
    print("   --ml-resource-group <your-ml-resource-group>") 
    print("   --ml-workspace <your-workspace-name>")
    print()
    
    # Show current subscription if available
    current_sub = get_current_subscription()
    if current_sub:
        print(f"💡 Your current Azure CLI subscription: {current_sub}")
    
    sys.exit(1)


def parse_time_to_cron(time_str: str, weekdays_only: bool = True) -> str:
    """Convert time string like '08:00' to cron expression."""
    try:
        hour, minute = time_str.split(':')
        hour = int(hour)
        minute = int(minute)
        
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("Invalid time range")
        
        # Cron format: second minute hour day month day-of-week
        days = "1-5" if weekdays_only else "*"  # Monday-Friday or every day
        return f"0 {minute} {hour} * * {days}"
        
    except (ValueError, IndexError):
        raise ValueError(f"Invalid time format: {time_str}. Use HH:MM format (e.g., '08:00')")


class AzureFunctionDeployer:
    """Handles Azure Function creation and deployment for ML cluster auto-scaling."""
    
    def __init__(
        self, 
        subscription_id: str, 
        ml_resource_group: str, 
        ml_workspace: str,
        function_resource_group: str = "eagle-functions-rg",
        function_app_name: str = "eagle-cluster-scaler", 
        storage_account: str = "eaglefunctionstorage",
        location: str = "East US",
        clusters: list = None,
        scale_up_cron: str = "0 0 8 * * 1-5",
        scale_down_cron: str = None
    ):
        self.subscription_id = subscription_id
        self.ml_resource_group = ml_resource_group
        self.ml_workspace = ml_workspace
        
        # Function App configuration (now configurable)
        self.resource_group = function_resource_group
        self.function_app_name = function_app_name
        self.storage_account = storage_account
        self.location = location
        self.clusters = clusters or ["eagle-cpu", "eagle-gpu-h100"]
        self.scale_up_cron = scale_up_cron
        self.scale_down_cron = scale_down_cron
        
        # Initialize Azure clients (lazy loading)
        self.credential = None
        self.resource_client = None
        self.storage_client = None
        self.web_client = None
        self.auth_client = None
        
    def _init_clients(self):
        """Initialize Azure SDK clients."""
        if self.credential is None:
            from azure.identity import AzureCliCredential
            from azure.mgmt.resource import ResourceManagementClient
            from azure.mgmt.storage import StorageManagementClient
            from azure.mgmt.web import WebSiteManagementClient
            from azure.mgmt.authorization import AuthorizationManagementClient
            
            # Use AzureCliCredential to explicitly use 'az login' session
            # This prevents issues with managed identity on Azure VMs
            self.credential = AzureCliCredential()
            self.resource_client = ResourceManagementClient(self.credential, self.subscription_id)
            self.storage_client = StorageManagementClient(self.credential, self.subscription_id)
            self.web_client = WebSiteManagementClient(self.credential, self.subscription_id)
            self.auth_client = AuthorizationManagementClient(self.credential, self.subscription_id)
        
    def create_resource_group(self) -> None:
        """Create resource group for the Function App."""
        print(f"📦 Creating resource group: {self.resource_group}")
        
        try:
            self._init_clients()
            self.resource_client.resource_groups.create_or_update(
                self.resource_group,
                {"location": self.location}
            )
            print(f"✅ Resource group {self.resource_group} created/updated")
        except Exception as e:
            print(f"❌ Failed to create resource group: {e}")
            raise
    
    def create_storage_account(self) -> str:
        """Create storage account and return connection string."""
        print(f"💾 Creating storage account: {self.storage_account}")
        
        try:
            self._init_clients()
            from azure.core.exceptions import ResourceExistsError
            
            # Create storage account
            storage_async_operation = self.storage_client.storage_accounts.begin_create(
                self.resource_group,
                self.storage_account,
                {
                    "sku": {"name": "Standard_LRS"},
                    "kind": "StorageV2",
                    "location": self.location,
                }
            )
            storage_account = storage_async_operation.result()
            print(f"✅ Storage account {self.storage_account} created")
            
        except ResourceExistsError:
            print(f"✅ Storage account {self.storage_account} already exists")
        except Exception as e:
            # Storage account might already exist, try to get connection string
            if "already exists" in str(e).lower():
                print(f"✅ Storage account {self.storage_account} already exists") 
            else:
                print(f"❌ Failed to create storage account: {e}")
                raise
        
        # Get connection string
        try:
            storage_keys = self.storage_client.storage_accounts.list_keys(
                self.resource_group, self.storage_account
            )
            storage_key = storage_keys.keys[0].value
            connection_string = (
                f"DefaultEndpointsProtocol=https;"
                f"AccountName={self.storage_account};"
                f"AccountKey={storage_key};"
                f"EndpointSuffix=core.windows.net"
            )
            return connection_string
        except Exception as e:
            print(f"❌ Failed to get storage connection string: {e}")
            raise
    
    def create_function_app(self, storage_connection_string: str) -> str:
        """Create Function App and return its principal ID."""
        print(f"⚡ Creating Function App: {self.function_app_name}")
        
        try:
            self._init_clients()
            
            # Create App Service Plan (Consumption)
            app_service_plan = {
                "location": self.location,
                "sku": {
                    "name": "Y1",
                    "tier": "Dynamic"
                }
            }
            
            plan_result = self.web_client.app_service_plans.begin_create_or_update(
                self.resource_group,
                f"{self.function_app_name}-plan",
                app_service_plan
            ).result()
            
            # Try different Function App configurations 
            configurations_to_try = [
                {
                    "name": "Auto-detect Python (no linuxFxVersion)",
                    "config": {
                        "location": self.location,
                        "kind": "functionapp,linux",
                        "properties": {
                            "serverFarmId": plan_result.id,
                            "siteConfig": {
                                "appSettings": [
                                    {"name": "AzureWebJobsStorage", "value": storage_connection_string},
                                    {"name": "FUNCTIONS_WORKER_RUNTIME", "value": "python"},
                                    {"name": "FUNCTIONS_EXTENSION_VERSION", "value": "~4"},
                                    {"name": "WEBSITE_RUN_FROM_PACKAGE", "value": "1"},
                                    {"name": "AZURE_SUBSCRIPTION_ID", "value": self.subscription_id},
                                    {"name": "AZURE_RESOURCE_GROUP", "value": self.ml_resource_group},
                                    {"name": "AZURE_ML_WORKSPACE_NAME", "value": self.ml_workspace},
                                    {"name": "CLUSTERS_TO_SCALE", "value": ",".join(self.clusters)},
                                    {"name": "SCALE_UP_CRON", "value": self.scale_up_cron},
                                    {"name": "SCALE_DOWN_CRON", "value": self.scale_down_cron or ""},
                                ],
                                "alwaysOn": False,
                                "functionAppScaleLimit": 1,
                                # No linuxFxVersion - let Azure auto-detect
                            }
                        },
                        "identity": {"type": "SystemAssigned"}
                    }
                },
                {
                    "name": "python|3.10 (lowercase)",
                    "config": {
                        "location": self.location,
                        "kind": "functionapp,linux", 
                        "properties": {
                            "serverFarmId": plan_result.id,
                            "siteConfig": {
                                "appSettings": [
                                    {"name": "AzureWebJobsStorage", "value": storage_connection_string},
                                    {"name": "FUNCTIONS_WORKER_RUNTIME", "value": "python"},
                                    {"name": "FUNCTIONS_EXTENSION_VERSION", "value": "~4"},
                                    {"name": "WEBSITE_RUN_FROM_PACKAGE", "value": "1"},
                                    {"name": "AZURE_SUBSCRIPTION_ID", "value": self.subscription_id},
                                    {"name": "AZURE_RESOURCE_GROUP", "value": self.ml_resource_group},
                                    {"name": "AZURE_ML_WORKSPACE_NAME", "value": self.ml_workspace},
                                    {"name": "CLUSTERS_TO_SCALE", "value": ",".join(self.clusters)},
                                    {"name": "SCALE_UP_CRON", "value": self.scale_up_cron},
                                    {"name": "SCALE_DOWN_CRON", "value": self.scale_down_cron or ""},
                                ],
                                "linuxFxVersion": "python|3.10",
                                "alwaysOn": False,
                                "functionAppScaleLimit": 1,
                            }
                        },
                        "identity": {"type": "SystemAssigned"}
                    }
                },
                {
                    "name": "PYTHON|3.9 (fallback version)",
                    "config": {
                        "location": self.location,
                        "kind": "functionapp,linux",
                        "properties": {
                            "serverFarmId": plan_result.id,
                            "siteConfig": {
                                "appSettings": [
                                    {"name": "AzureWebJobsStorage", "value": storage_connection_string},
                                    {"name": "FUNCTIONS_WORKER_RUNTIME", "value": "python"},
                                    {"name": "FUNCTIONS_EXTENSION_VERSION", "value": "~4"},
                                    {"name": "WEBSITE_RUN_FROM_PACKAGE", "value": "1"},
                                    {"name": "AZURE_SUBSCRIPTION_ID", "value": self.subscription_id},
                                    {"name": "AZURE_RESOURCE_GROUP", "value": self.ml_resource_group},
                                    {"name": "AZURE_ML_WORKSPACE_NAME", "value": self.ml_workspace},
                                    {"name": "CLUSTERS_TO_SCALE", "value": ",".join(self.clusters)},
                                    {"name": "SCALE_UP_CRON", "value": self.scale_up_cron},
                                    {"name": "SCALE_DOWN_CRON", "value": self.scale_down_cron or ""},
                                ],
                                "linuxFxVersion": "PYTHON|3.9",
                                "alwaysOn": False,
                                "functionAppScaleLimit": 1,
                            }
                        },
                        "identity": {"type": "SystemAssigned"}
                    }
                }
            ]
            
            function_app = None
            for attempt in configurations_to_try:
                try:
                    print(f"🐍 Trying: {attempt['name']}")
                    function_app = self.web_client.web_apps.begin_create_or_update(
                        self.resource_group,
                        self.function_app_name,
                        attempt['config']
                    ).result()
                    
                    print(f"✅ Function App {self.function_app_name} created successfully with {attempt['name']}")
                    break
                    
                except Exception as e:
                    error_msg = str(e)
                    print(f"⚠️  Failed with {attempt['name']}: {error_msg[:100]}...")
                    if attempt != configurations_to_try[-1]:  # Not the last attempt
                        print("   Trying next configuration...")
                        continue
                    else:
                        raise Exception(f"All Function App configuration attempts failed. Last error: {e}")
            
            if function_app is None:
                raise Exception("Failed to create Function App with any configuration")
            
            # Get the managed identity principal ID
            function_identity = self.web_client.web_apps.get(
                self.resource_group, self.function_app_name
            )
            principal_id = function_identity.identity.principal_id
            print(f"🔑 Managed Identity Principal ID: {principal_id}")
            
            # Fix runtime configuration to ensure Python is properly detected
            print("🔧 Updating runtime configuration...")
            self._fix_python_runtime()
            
            return principal_id
            
        except Exception as e:
            print(f"❌ Failed to create Function App: {e}")
            raise
    
    def _fix_python_runtime(self):
        """Fix Python runtime configuration post-deployment."""
        try:
            # Get current configuration
            current_config = self.web_client.web_apps.get_configuration(
                self.resource_group, self.function_app_name
            )
            
            # Update site config with explicit Python runtime settings
            site_config = {
                "linux_fx_version": "Python|3.10",  # Use different property name
                "app_settings": [
                    {"name": "FUNCTIONS_WORKER_RUNTIME", "value": "python"},
                    {"name": "FUNCTIONS_EXTENSION_VERSION", "value": "~4"},
                    {"name": "WEBSITE_RUN_FROM_PACKAGE", "value": "1"},
                    {"name": "PYTHON_THREADPOOL_THREAD_COUNT", "value": "1"},
                ]
            }
            
            # Update the configuration
            self.web_client.web_apps.update_configuration(
                self.resource_group,
                self.function_app_name,
                site_config
            )
            
            print("✅ Python runtime configuration updated")
            
        except Exception as e:
            print(f"⚠️  Warning: Could not update runtime configuration: {e}")
            print("   This may resolve automatically after deployment")
    
    def create_deployment_package(self) -> str:
        """Create deployment package with function code."""
        print("📦 Creating deployment package...")
        
        current_dir = Path(__file__).parent
        package_path = current_dir / "deploy.zip"
        
        # Generate custom function_app.py with correct schedules
        custom_function_app = self._generate_function_app_code()
        
        # Files to include in deployment
        files_to_deploy = {
            "requirements.txt": current_dir / "requirements.txt", 
            "host.json": current_dir / "host.json",
        }
        
        try:
            with zipfile.ZipFile(package_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add generated function_app.py
                zipf.writestr("function_app.py", custom_function_app)
                print(f"  ✅ Added function_app.py (generated with custom schedules)")
                
                # Add other files
                for archive_name, file_path in files_to_deploy.items():
                    if file_path.exists():
                        zipf.write(file_path, archive_name)
                        print(f"  ✅ Added {archive_name}")
                    else:
                        print(f"  ❌ Warning: {file_path} not found")
            
            print(f"✅ Deployment package created: {package_path}")
            return str(package_path)
            
        except Exception as e:
            print(f"❌ Failed to create deployment package: {e}")
            raise
    
    def _generate_function_app_code(self) -> str:
        """Generate function_app.py with custom schedules."""
        scale_down_function = ""
        
        # Only include scale-down function if schedule is provided
        if self.scale_down_cron:
            scale_down_function = f'''

@app.timer_trigger(
    schedule="{self.scale_down_cron}",
    arg_name="mytimer", 
    run_on_startup=False,
    use_monitor=False
)
def scale_down_clusters(mytimer: func.TimerRequest) -> None:
    """
    Timer-triggered function to scale down Azure ML compute clusters.
    
    This function scales clusters back to min_instances=0 to save costs.
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
                logging.info(f"Scaling down cluster: {{cluster_name}}")
                if scale_cluster_min_nodes(ml_client, cluster_name, min_nodes=0):
                    success_count += 1
                else:
                    logging.warning(f"Failed to scale down cluster: {{cluster_name}}")
        
        logging.info(f"Scale-down completed. Successfully updated {{success_count}}/{{len(clusters_to_scale)}} clusters")
        
    except Exception as e:
        logging.error(f"Scale-down function failed with error: {{str(e)}}")
'''

        return f'''"""
Azure Function to scale Azure ML compute cluster minimum nodes.

This function is triggered on a schedule to increase/decrease the minimum nodes
for specified Azure ML compute clusters. This ensures clusters are pre-warmed
and ready for immediate job execution while managing costs.

Generated automatically by setup_scheduled_scaling.py
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
CLUSTERS_TO_SCALE = os.environ.get("CLUSTERS_TO_SCALE", "{','.join(self.clusters)}")

app = func.FunctionApp()


def get_clusters_list() -> list:
    """Parse clusters list from environment variable."""
    return [cluster.strip() for cluster in CLUSTERS_TO_SCALE.split(',') if cluster.strip()]


def get_ml_client() -> MLClient:
    """Create and return an authenticated MLClient."""
    # Note: In Azure Functions, DefaultAzureCredential works correctly with Managed Identity
    # This is different from the deployment script which runs on Azure VMs
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
            logging.error(f"Cluster {{cluster_name}} is not an AmlCompute cluster")
            return False
        
        current_min = cluster.min_instances
        logging.info(f"Current min_instances for {{cluster_name}}: {{current_min}}")
        
        if current_min >= min_nodes:
            logging.info(f"Cluster {{cluster_name}} already has min_instances >= {{min_nodes}}, no action needed")
            return True
        
        # Update cluster configuration
        cluster.min_instances = min_nodes
        
        # Apply the update
        logging.info(f"Updating {{cluster_name}} min_instances from {{current_min}} to {{min_nodes}}...")
        ml_client.compute.begin_create_or_update(cluster).result()
        
        logging.info(f"Successfully updated {{cluster_name}} min_instances to {{min_nodes}}")
        return True
        
    except Exception as e:
        logging.error(f"Failed to update cluster {{cluster_name}}: {{str(e)}}")
        return False


@app.timer_trigger(
    schedule="{self.scale_up_cron}",
    arg_name="mytimer",
    run_on_startup=False,
    use_monitor=False
)
def scale_up_clusters(mytimer: func.TimerRequest) -> None:
    """
    Timer-triggered function to scale up Azure ML compute clusters.
    
    Schedule: {self.scale_up_cron}
    """
    logging.info("Scale-up function starting...")
    
    # Validate environment variables
    if not all([SUBSCRIPTION_ID, RESOURCE_GROUP, WORKSPACE_NAME]):
        logging.error("Missing required environment variables")
        logging.error(f"AZURE_SUBSCRIPTION_ID: {{'✓' if SUBSCRIPTION_ID else '✗'}}")
        logging.error(f"AZURE_RESOURCE_GROUP: {{'✓' if RESOURCE_GROUP else '✗'}}")
        logging.error(f"AZURE_ML_WORKSPACE_NAME: {{'✓' if WORKSPACE_NAME else '✗'}}")
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
                logging.info(f"Processing cluster: {{cluster_name}}")
                if scale_cluster_min_nodes(ml_client, cluster_name, min_nodes=1):
                    success_count += 1
                else:
                    logging.warning(f"Failed to scale cluster: {{cluster_name}}")
        
        logging.info(f"Scale-up completed. Successfully updated {{success_count}}/{{len(clusters_to_scale)}} clusters")
        
    except Exception as e:
        logging.error(f"Scale-up function failed with error: {{str(e)}}")
{scale_down_function}
'''
    
    def deploy_function_code(self, package_path: str) -> None:
        """Deploy function code - provide manual instructions."""
        print("📤 Function code deployment ready...")
        print("💡 To complete deployment, run:")
        print(f"   cd {Path(__file__).parent}")
        print(f"   func azure functionapp publish {self.function_app_name}")
        print("   (Install Azure Functions Core Tools if needed)")
    
    def assign_ml_permissions(self, principal_id: str) -> None:
        """Assign ML Compute Operator permissions to the Function App."""
        print("🔐 Assigning ML permissions...")
        
        try:
            self._init_clients()
            
            # ML workspace scope
            ml_scope = (
                f"/subscriptions/{self.subscription_id}"
                f"/resourceGroups/{self.ml_resource_group}"
                f"/providers/Microsoft.MachineLearningServices/workspaces/{self.ml_workspace}"
            )
            
            # Azure Machine Learning Compute Operator role
            ml_compute_role_id = "f1c88694-1075-4de2-a3e5-c5c4c4f26b71"
            role_definition_id = f"/subscriptions/{self.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/{ml_compute_role_id}"
            
            # Create role assignment
            role_assignment = {
                "role_definition_id": role_definition_id,
                "principal_id": principal_id,
                "principal_type": "ServicePrincipal"
            }
            
            # Generate unique assignment name
            assignment_name = str(uuid.uuid4())
            
            self.auth_client.role_assignments.create(
                scope=ml_scope,
                role_assignment_name=assignment_name,
                parameters=role_assignment
            )
            
            print(f"✅ Assigned ML Compute Operator role to Function App")
            
        except Exception as e:
            print(f"⚠️  Role assignment may need manual setup: {e}")
            print("🔑 Manual role assignment command:")
            print(f"   az role assignment create \\")
            print(f"     --assignee {principal_id} \\")
            print(f"     --role 'Azure Machine Learning Compute Operator' \\")
            print(f"     --scope '{ml_scope}'")
    
    def verify_deployment(self) -> None:
        """Verify the function app is working."""
        print("🔍 Verifying deployment...")
        
        try:
            self._init_clients()
            function_app = self.web_client.web_apps.get(
                self.resource_group, self.function_app_name
            )
            
            if function_app.state == "Running":
                print("✅ Function App is running")
            else:
                print(f"⚠️  Function App state: {function_app.state}")
                
        except Exception as e:
            print(f"❌ Verification failed: {e}")
    
    def deploy_all(self) -> None:
        """Execute complete deployment process."""
        print("🚀 Starting Azure Function deployment for ML cluster auto-scaler")
        print("=" * 70)
        
        try:
            # Step 1: Create resource group
            self.create_resource_group()
            
            # Step 2: Create storage account
            storage_connection = self.create_storage_account()
            
            # Step 3: Create Function App
            principal_id = self.create_function_app(storage_connection)
            
            # Step 4: Create deployment package
            package_path = self.create_deployment_package()
            
            # Step 5: Deploy function code
            self.deploy_function_code(package_path)
            
            # Step 6: Assign ML permissions
            self.assign_ml_permissions(principal_id)
            
            # Step 7: Verify deployment
            self.verify_deployment()
            
            print("\n" + "=" * 70)
            print("✅ Azure Function infrastructure deployed successfully!")
            
        except Exception as e:
            print(f"\n❌ Deployment failed: {e}")
            sys.exit(1)


def install_dependencies():
    """Install required Azure SDK packages."""
    print("📦 Installing Azure SDK dependencies...")
    
    requirements_file = Path(__file__).parent / "deploy_requirements.txt"
    
    try:
        subprocess.run([
            sys.executable, "-m", "pip", "install", "-r", str(requirements_file)
        ], check=True, capture_output=True, text=True)
        print("✅ Dependencies installed")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        print("💡 Try: pip install -r aml/scripts/scaling/deploy_requirements.txt")
        return False
    
    return True


def validate_config(subscription_id: str, resource_group: str, workspace_name: str):
    """Validate Azure ML configuration."""
    print("🔍 Validating configuration...")
    
    missing = []
    if not subscription_id:
        missing.append("subscription_id")
    if not resource_group:
        missing.append("resource_group") 
    if not workspace_name:
        missing.append("workspace_name")
    
    if missing:
        print("❌ Missing required arguments:")
        for item in missing:
            print(f"   - {item}")
        return False
    
    print("✅ Configuration validated")
    print(f"   Subscription: {subscription_id}")
    print(f"   Resource Group: {resource_group}")
    print(f"   Workspace: {workspace_name}")
    return True


def run_deployment(
    subscription_id: str, 
    resource_group: str, 
    workspace_name: str,
    function_resource_group: str,
    function_app_name: str,
    storage_account: str,
    location: str,
    clusters: list,
    scale_up_cron: str,
    scale_down_cron: str = None
):
    """Run the Azure Function deployment."""
    print("\n🚀 Starting Azure Function deployment...")
    
    try:
        # Create deployer and run deployment
        deployer = AzureFunctionDeployer(
            subscription_id=subscription_id,
            ml_resource_group=resource_group,
            ml_workspace=workspace_name,
            function_resource_group=function_resource_group,
            function_app_name=function_app_name,
            storage_account=storage_account,
            location=location,
            clusters=clusters,
            scale_up_cron=scale_up_cron,
            scale_down_cron=scale_down_cron
        )
        
        deployer.deploy_all()
        
        print("\n🎉 Azure Function deployed successfully!")
        
        print("\n📋 What's Next:")
        print("================")
        print("1. Your Function App will scale ML clusters according to this schedule:")
        if scale_down_cron:
            print(f"   📈 Scale UP:   {scale_up_cron} (sets min_instances=1)")  
            print(f"   📉 Scale DOWN: {scale_down_cron} (sets min_instances=0)")
        else:
            print(f"   📈 Scale UP:   {scale_up_cron} (sets min_instances=1)")
            print(f"   📉 Scale DOWN: Disabled (clusters stay at min_instances=1)")
        print()
        print("2. Monitored clusters:")
        for cluster in clusters:
            print(f"   🖥️  {cluster}")
        print()
        print("3. Deploy function code (if needed):")
        print("   cd aml/scripts/scaling")
        print(f"   func azure functionapp publish {function_app_name}")
        print()
        print("4. Test the function:")
        print("   az functionapp function invoke \\")
        print(f"     --name {function_app_name} \\")
        print(f"     --resource-group {function_resource_group} \\")
        print("     --function-name scale_up_clusters")
        print()
        print("5. Monitor logs in Azure Portal > Application Insights")
        print("   🌐 https://portal.azure.com")
        
    except Exception as e:
        print(f"❌ Deployment failed: {e}")
        sys.exit(1)


def main():
    """Main setup process."""
    parser = argparse.ArgumentParser(
        description="Deploy Azure Function for ML cluster scheduled auto-scaling",
        epilog="""
Examples:
  # Minimal - uses current 'az login' subscription automatically
  python setup_scheduled_scaling.py --ml-resource-group my-ml-rg --ml-workspace my-workspace
  
  # Using YAML configuration file  
  python setup_scheduled_scaling.py --config schedule.yml
  
  # Custom clusters and schedule (auto-detects subscription)
  python setup_scheduled_scaling.py --ml-resource-group my-ml-rg --ml-workspace my-workspace \\
    --clusters "cpu-cluster,gpu-cluster" --scale-up "07:30" --scale-down "18:30"
  
  # Override subscription if needed
  python setup_scheduled_scaling.py --subscription-id 12345... --ml-resource-group my-ml-rg --ml-workspace my-workspace

Note: subscription-id is automatically detected from 'az login' if not specified
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Configuration file option
    config_help = "YAML configuration file (alternative to command line arguments)"
    if not HAS_YAML_SUPPORT:
        config_help += " [requires: pip install pyyaml>=6.0]"
    
    parser.add_argument("--config", type=str, help=config_help)
    
    # Required arguments (can be provided via YAML or auto-detected)
    parser.add_argument("--subscription-id", help="Azure subscription ID (auto-detected from 'az login' if not specified)")
    parser.add_argument("--ml-resource-group", help="ML workspace resource group")
    parser.add_argument("--ml-workspace", help="ML workspace name")
    
    # Cluster and scheduling arguments
    parser.add_argument("--clusters", default="eagle-cpu,eagle-gpu-h100", 
                       help="Comma-separated list of cluster names to scale (default: eagle-cpu,eagle-gpu-h100)")
    parser.add_argument("--scale-up", default="08:00", 
                       help="Scale up time in HH:MM format, 24-hour UTC (default: 08:00)")
    parser.add_argument("--scale-down", 
                       help="Optional scale down time in HH:MM format, 24-hour UTC. If not specified, clusters stay scaled up")
    parser.add_argument("--weekdays-only", action="store_true", default=True,
                       help="Only scale on weekdays (Monday-Friday). Default: True")
    parser.add_argument("--all-days", action="store_true", 
                       help="Scale every day of the week (overrides --weekdays-only)")
    
    # Function App configuration arguments  
    parser.add_argument("--function-resource-group", default="eagle-functions-rg", 
                       help="Resource group for Function App (default: eagle-functions-rg)")
    parser.add_argument("--function-name", default="eagle-cluster-scaler", 
                       help="Function App name (default: eagle-cluster-scaler)")
    parser.add_argument("--storage-account", default="eaglefunctionstorage",
                       help="Storage account name (default: eaglefunctionstorage)")
    parser.add_argument("--location", default="East US", 
                       help="Azure region for resources (default: East US)")
    
    args = parser.parse_args()
    
    # Load and merge configuration
    config = {}
    if args.config:
        config = load_yaml_config(args.config)
        print(f"✅ Loaded configuration from {args.config}")
    
    # Merge YAML config with CLI arguments (CLI takes precedence)
    final_config = merge_config_with_args(config, args)
    
    # Auto-detect subscription ID if needed and validate all required config
    validate_merged_config(final_config)
    
    print("⚡ Azure Function Setup for ML Cluster Scheduled Auto-Scaling")
    print("=" * 65)
    
    # Extract values with proper key handling
    subscription_id = final_config.get('subscription_id') or final_config.get('subscription-id')
    ml_resource_group = final_config.get('ml_resource_group') or final_config.get('ml-resource-group') 
    ml_workspace = final_config.get('ml_workspace') or final_config.get('ml-workspace')
    clusters_str = final_config.get('clusters', 'eagle-cpu,eagle-gpu-h100')
    scale_up = final_config.get('scale_up') or final_config.get('scale-up', '08:00')
    scale_down = final_config.get('scale_down') or final_config.get('scale-down')
    weekdays_only = final_config.get('weekdays_only', True) and not final_config.get('all_days', False)
    function_resource_group = final_config.get('function_resource_group') or final_config.get('function-resource-group', 'eagle-functions-rg')
    function_name = final_config.get('function_name') or final_config.get('function-name', 'eagle-cluster-scaler')
    storage_account = final_config.get('storage_account') or final_config.get('storage-account', 'eaglefunctionstorage')
    location = final_config.get('location', 'East US')
    
    # Parse clusters list
    if isinstance(clusters_str, list):
        clusters = clusters_str
    else:
        clusters = [cluster.strip() for cluster in clusters_str.split(',') if cluster.strip()]
    
    try:
        scale_up_cron = parse_time_to_cron(scale_up, weekdays_only)
        scale_down_cron = None
        if scale_down:
            scale_down_cron = parse_time_to_cron(scale_down, weekdays_only)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)
    
    # Display configuration
    print("📋 Configuration:")
    print(f"   Subscription: {subscription_id}")
    print(f"   ML Resource Group: {ml_resource_group}")
    print(f"   ML Workspace: {ml_workspace}")
    print(f"   Clusters: {', '.join(clusters)}")
    print(f"   Scale Up: {scale_up} UTC ({'weekdays' if weekdays_only else 'daily'})")
    if scale_down_cron:
        print(f"   Scale Down: {scale_down} UTC ({'weekdays' if weekdays_only else 'daily'})")
    else:
        print(f"   Scale Down: Disabled (clusters will stay scaled up)")
    print(f"   Function App: {function_name} (in {function_resource_group})")
    print(f"   Location: {location}")
    
    # Step 1: Install dependencies
    if not install_dependencies():
        sys.exit(1)
    
    # Step 2: Validate configuration  
    if not validate_config(subscription_id, ml_resource_group, ml_workspace):
        sys.exit(1)
    
    # Step 3: Run deployment
    run_deployment(
        subscription_id=subscription_id,
        resource_group=ml_resource_group, 
        workspace_name=ml_workspace,
        function_resource_group=function_resource_group,
        function_app_name=function_name,
        storage_account=storage_account,
        location=location,
        clusters=clusters,
        scale_up_cron=scale_up_cron,
        scale_down_cron=scale_down_cron
    )


if __name__ == "__main__":
    main()