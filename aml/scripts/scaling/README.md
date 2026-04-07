# Azure Function: ML Compute Cluster Scheduled Auto-Scaler

This Azure Function automatically scales Azure Machine Learning compute clusters from minimum 0 nodes to 1 node based on a schedule. This ensures clusters are pre-warmed and ready for immediate job execution during business hours.

## Overview

**What it does:**
- 🕐 **Scale Up**: Increases min nodes from 0 to 1 at 8 AM UTC Monday-Friday
- 🕕 **Scale Down** (optional): Decreases min nodes back to 0 at 6 PM UTC Monday-Friday
- 💰 **Cost Optimization**: Prevents cold start delays while managing compute costs
- 🔄 **Automated**: Runs on schedule without manual intervention

**Supported Clusters:**
- CPU Cluster: `eagle-cpu`
- GPU Cluster: `eagle-gpu-h100`

## Files in this directory

- **`setup_scheduled_scaling.py`** - **Complete deployment script** (run this!)
- **`schedule.yml`** - **Example YAML configuration file** (copy and customize)
- **`function_app.py`** - The actual Azure Function timer-triggered code
- **`requirements.txt`** - Python packages for the Azure Function runtime
- **`deploy_requirements.txt`** - Python packages for deployment script
- **`host.json`** - Azure Function configuration settings
- **`local.settings.json`** - Local development configuration template

## Prerequisites

1. **Azure CLI**: `az login` (already authenticated)
2. **Azure ML Workspace** and compute clusters already exist
3. **Python 3.9+** for running the deployment script

**Optional:**
- Configure `aml/config.py` (if you prefer not to use command line arguments)

## Configuration

### Environment Variables

The function requires these environment variables to be configured:

| Variable | Description | Example |
|----------|-------------|---------|
| `AZURE_SUBSCRIPTION_ID` | Your Azure subscription ID | `12345678-1234-5678-9012-123456789012` |
| `AZURE_RESOURCE_GROUP` | Resource group containing ML workspace | `eagle-ml-rg` |
| `AZURE_ML_WORKSPACE_NAME` | Name of Azure ML workspace | `eagle-ml-workspace` |
| `CPU_CLUSTER_NAME` | CPU compute cluster name | `eagle-cpu` |
| `GPU_CLUSTER_NAME` | GPU compute cluster name | `eagle-gpu-h100` |

### Schedule Configuration

The function uses cron expressions for scheduling:

```python
# Scale UP: 8 AM UTC, Monday-Friday
schedule="0 0 8 * * 1-5"

# Scale DOWN: 6 PM UTC, Monday-Friday  
schedule="0 0 18 * * 1-5"
```

**Cron Format**: `{second} {minute} {hour} {day} {month} {day-of-week}`
- `0 0 8 * * 1-5` = 8:00 AM UTC, weekdays
- `0 0 18 * * 1-5` = 6:00 PM UTC, weekdays

**Common Schedule Examples:**
```bash
# Every weekday at 9 AM UTC
"0 0 9 * * 1-5"

# Every day at 7:30 AM UTC
"0 30 7 * * *"

# Business hours only (Mon-Fri 8 AM-5 PM UTC)
"0 0 8 * * 1-5"  # Scale up
"0 0 17 * * 1-5" # Scale down
```

## Quick Deployment

### 🚀 One-Command Setup (Recommended)

**Option 1: Command Line Arguments (Recommended)**

```bash
# Minimal deployment - uses current 'az login' subscription automatically
python aml/scripts/scaling/setup_scheduled_scaling.py \
  --ml-resource-group <your-ml-resource-group> \
  --ml-workspace <your-workspace-name>

# Custom clusters and schedule
python aml/scripts/scaling/setup_scheduled_scaling.py \
  --ml-resource-group <your-ml-resource-group> \
  --ml-workspace <your-workspace-name> \
  --clusters "my-cpu-cluster,my-gpu-cluster" \
  --scale-up "07:30" \
  --scale-down "18:30"

# Custom function app settings
python aml/scripts/scaling/setup_scheduled_scaling.py \
  --ml-resource-group <your-ml-resource-group> \
  --ml-workspace <your-workspace-name> \
  --function-resource-group my-functions-rg \
  --function-name my-cluster-scaler \
  --location "West US 2"

# Override subscription if needed (optional)
python aml/scripts/scaling/setup_scheduled_scaling.py \
  --subscription-id <specific-subscription-id> \
  --ml-resource-group <your-ml-resource-group> \
  --ml-workspace <your-workspace-name>
```

**Available Arguments:**
- `--subscription-id` (required): Azure subscription ID
- `--ml-resource-group` (required): ML workspace resource group  
- `--ml-workspace` (required): ML workspace name
- `--clusters`: Comma-separated cluster names (default: eagle-cpu,eagle-gpu-h100)
- `--scale-up`: Scale up time HH:MM UTC (default: 08:00)
- `--scale-down`: Optional scale down time HH:MM UTC
- `--all-days`: Scale every day (default: weekdays only)
- `--function-resource-group`: Function App resource group (default: eagle-functions-rg)
- `--function-name`: Function App name (default: eagle-cluster-scaler)
- `--storage-account`: Storage account name (default: eaglefunctionstorage)
- `--location`: Azure region (default: East US)

**Option 2: YAML Configuration File (New!)**

Create a `schedule.yml` file with your configuration:

```yaml
# Azure subscription and ML workspace details
# Note: subscription-id is optional - auto-detected from 'az login' if not specified
ml-resource-group: "your-ml-resource-group"
ml-workspace: "your-ml-workspace-name"

# Cluster scaling configuration
clusters:
  - "eagle-cpu"
  - "eagle-gpu-h100"

# Scheduling (all times in UTC)
scale-up: "08:00"      # Scale to min=1 at 8:00 AM UTC
scale-down: "18:00"    # Scale to min=0 at 6:00 PM UTC (optional)
weekdays-only: true    # Only scale Monday-Friday

# Azure Function settings (optional, uses defaults if not specified)
function-resource-group: "eagle-functions-rg" 
function-name: "eagle-cluster-scaler"
location: "East US"
```

Then deploy with:

```bash
# Deploy using YAML configuration
python aml/scripts/scaling/setup_scheduled_scaling.py --config schedule.yml

# Use YAML config with command line overrides (CLI takes precedence)
python aml/scripts/scaling/setup_scheduled_scaling.py \
  --config schedule.yml \
  --scale-up "07:00" \
  --clusters "prod-cluster-only"
```

**YAML Configuration Benefits:**
- ✅ Easier to manage complex configurations
- ✅ Version control friendly
- ✅ Supports both list and string formats for clusters
- ✅ Command line arguments can still override YAML values
- ✅ Better for teams sharing configurations

**Option 3: Using aml/config.py (Legacy)**

If you have `aml/config.py` configured with subscription details:

```bash
# This option is deprecated, use command line arguments instead
python aml/scripts/scaling/setup_scheduled_scaling.py
```

**The script will:**
✅ Install required Azure SDK packages automatically  
✅ Create all Azure resources (Resource Group, Storage, Function App)  
✅ Configure the Function App with your specific ML workspace and cluster settings  
✅ Generate function code with your custom schedules  
✅ Set up managed identity and permissions  
✅ Create deployment package ready for Azure

**Get your Azure details:**

```bash
# Current subscription
az account show --query id -o tsv

# Find ML workspaces in your subscription
az ml workspace list --query "[].{name:name, resourceGroup:resourceGroup, location:location}" -o table

# List compute clusters in a workspace
az ml compute list --workspace-name <workspace-name> --resource-group <resource-group> --query "[].name" -o table
```

## Common Usage Examples

**Basic setup with defaults (8 AM scale up, weekdays only):**
```bash
python aml/scripts/scaling/setup_scheduled_scaling.py \
  --ml-resource-group my-ml-rg \
  --ml-workspace my-workspace
```

**Early morning pre-warming for heavy workloads:**
```bash
python aml/scripts/scaling/setup_scheduled_scaling.py \
  --ml-resource-group my-ml-rg \
  --ml-workspace my-workspace \
  --scale-up "06:00" \
  --scale-down "20:00"
```

**24/7 operation with daily cycling:**
```bash
python aml/scripts/scaling/setup_scheduled_scaling.py \
  --ml-resource-group my-ml-rg \
  --ml-workspace my-workspace \
  --scale-up "08:00" \
  --scale-down "02:00" \
  --all-days
```

**Custom clusters with different naming:**
```bash
python aml/scripts/scaling/setup_scheduled_scaling.py \
  --ml-resource-group my-ml-rg \
  --ml-workspace my-workspace \
  --clusters "production-cpu,production-gpu,staging-cluster"
```

**Always-on mode (no scale down):**
```bash
python aml/scripts/scaling/setup_scheduled_scaling.py \
  --ml-resource-group my-ml-rg \
  --ml-workspace my-workspace \
  --scale-up "08:00"
  # No --scale-down argument = clusters stay scaled up
```

### YAML Configuration Examples

**Basic setup with YAML:**

Create `my-schedule.yml`:
```yaml
ml-resource-group: "my-ml-rg"
ml-workspace: "my-workspace"
# Uses defaults: 8 AM scale up, weekdays only, default clusters
# Note: subscription auto-detected from 'az login'
```

Deploy:
```bash
python aml/scripts/scaling/setup_scheduled_scaling.py --config my-schedule.yml
```

**Early morning pre-warming with YAML:**

Create `early-schedule.yml`:
```yaml
ml-resource-group: "my-ml-rg"
ml-workspace: "my-workspace"
scale-up: "06:00"
scale-down: "20:00"
# Note: subscription auto-detected from 'az login'
```

**24/7 operation with YAML:**

Create `always-on-schedule.yml`:
```yaml
ml-resource-group: "my-ml-rg"
ml-workspace: "my-workspace"
scale-up: "08:00"
scale-down: "02:00"
weekdays-only: false
all-days: true
# Note: subscription auto-detected from 'az login'
```

**Custom clusters with YAML:**

Create `production-schedule.yml`:
```yaml
ml-resource-group: "production-ml-rg"
ml-workspace: "production-workspace"
clusters:
  - "production-cpu"
  - "production-gpu"
  - "staging-cluster"
function-name: "production-cluster-scaler"
function-resource-group: "production-functions-rg"
# Note: subscription auto-detected from 'az login'
```

**Always-on mode with YAML:**

Create `always-on-schedule.yml`:
```yaml
ml-resource-group: "my-ml-rg"
ml-workspace: "my-workspace"
scale-up: "08:00"
# No scale-down = clusters stay scaled up 24/7
# Note: subscription auto-detected from 'az login'
```

### Manual Advanced Setup

If you need more control over the deployment process:

**Install dependencies:**
```bash
pip install -r aml/scripts/deploy_requirements.txt
```

**Run deployment script directly:**
```bash
python aml/scripts/deploy_function.py \
  --subscription-id <your-subscription-id> \
  --ml-resource-group <your-ml-resource-group> \
  --ml-workspace <your-workspace-name>
```

**Deploy function code manually (if needed):**
```bash
cd aml/scripts
func azure functionapp publish eagle-cluster-scaler
```

## Authentication

The function uses **Managed Identity** for secure authentication:

1. **System-assigned managed identity** is automatically enabled for the Function App
2. **No secrets or connection strings** are stored in the application
3. **Azure RBAC** controls access to ML workspace

### Required Permissions

The Function App's managed identity needs these permissions on the ML workspace:

- **Azure Machine Learning Compute Operator**: Modify compute clusters
- **Reader**: Read workspace and cluster configurations

**Assign permissions:**
```bash
# Get the Function App's managed identity
PRINCIPAL_ID=$(az functionapp show \
  --name eagle-cluster-scaler \
  --resource-group eagle-functions-rg \
  --query identity.principalId -o tsv)

# Assign ML Compute Operator role
az role assignment create \
  --assignee $PRINCIPAL_ID \
  --role "Azure Machine Learning Compute Operator" \
  --scope "/subscriptions/<subscription-id>/resourceGroups/<ml-rg>/providers/Microsoft.MachineLearningServices/workspaces/<workspace-name>"
```

## Local Development

1. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Local Settings:**
   ```bash
   # Update local.settings.json with your values
   cd aml/scripts
   cp local.settings.json.template local.settings.json
   # Edit with actual subscription ID, resource group, etc.
   ```

3. **Install Azure Functions Core Tools:**
   ```bash
   npm install -g azure-functions-core-tools@4 --unsafe-perm true
   ```

4. **Run Locally:**
   ```bash
   func start
   ```

5. **Test Functions Manually:**
   ```bash
   # Test scale-up function
   curl -X POST "http://localhost:7071/admin/functions/scale_up_clusters" \
        -H "Content-Type: application/json" \
        -d '{}'
   ```

## Monitoring

### Application Insights

- **Logs**: View function execution logs and errors
- **Metrics**: Monitor execution time and success rates  
- **Alerts**: Set up notifications for failures

### Log Analysis Queries

```kusto
// Function execution success rate
requests
| where name startswith "scale_"
| summarize 
    Total = count(),
    Success = countif(success == true),
    SuccessRate = round(countif(success == true) * 100.0 / count(), 2)
by name

// Recent errors
traces
| where severityLevel >= 3
| where timestamp > ago(1d)
| order by timestamp desc
```

### Azure Monitor Alerts

Create alerts for:
- **Function failures** (success rate < 90%)
- **Missing executions** (no runs for > 2 hours during business hours)
- **Long execution times** (duration > 5 minutes)

## Troubleshooting

### Common Issues

1. **Authentication Errors**
   ```
   DefaultAzureCredential failed to retrieve a token
   ```
   **Solution**: Verify managed identity and RBAC permissions

2. **Cluster Not Found**
   ```
   Compute cluster 'eagle-cpu' not found
   ```
   **Solution**: Check cluster names and workspace configuration

3. **Schedule Not Working**
   ```
   Function not triggering at expected times
   ```
   **Solution**: Verify timezone (UTC) and cron expression format

### Debug Steps

1. **Check Application Settings** in Azure Portal
2. **Review Function Logs** in Application Insights
3. **Test Authentication** locally with Azure CLI `az ml compute list`
4. **Verify Cluster Exists** in Azure ML Studio

### Manual Testing

```bash
# Test scale-up function via Azure CLI
az functionapp function invoke \
  --name eagle-cluster-scaler \
  --resource-group eagle-functions-rg \
  --function-name scale_up_clusters
```

## Cost Optimization

### Consumption vs. Premium Plans

- **Consumption**: Pay per execution (~$0.0001/execution)
- **Premium**: Always-on, faster cold start (~$50-180/month)

For scheduled jobs that run 2x daily, **Consumption plan** is most cost-effective.

### Cluster Cost Impact

- **Cold start delay**: 3-5 minutes to scale from 0→1 nodes
- **Pre-warmed cost**: ~$1-5/hour for min_instances=1 (varies by VM size)
- **Break-even**: If you run ML jobs >1-2 times/day, pre-warming saves time

## Security Best Practices

1. ✅ **Use Managed Identity** (no secrets in code)
2. ✅ **Principle of least privilege** (minimal RBAC permissions)
3. ✅ **Environment-specific settings** (dev/staging/prod)
4. ✅ **Monitor access logs** in Azure Activity Log
5. ✅ **Use private endpoints** for high-security environments

## Customization

### Adding More Clusters

Edit the function to include additional clusters:

```python
clusters_to_scale = [
    "eagle-cpu",
    "eagle-gpu-h100", 
    "eagle-special-cluster",  # Add new clusters here
]
```

### Different Schedules per Cluster

Create separate functions with different schedules:

```python
@app.timer_trigger(schedule="0 0 6 * * 1-5", ...)  # Early morning
def scale_up_gpu_early(mytimer):
    scale_cluster_min_nodes(ml_client, "eagle-gpu-h100", 1)

@app.timer_trigger(schedule="0 0 8 * * 1-5", ...)  # Regular hours
def scale_up_cpu_regular(mytimer):
    scale_cluster_min_nodes(ml_client, "eagle-cpu", 1)
```

### Scaling to Multiple Nodes

Modify the `min_nodes` parameter:

```python
# Scale to 2 nodes minimum
scale_cluster_min_nodes(ml_client, cluster_name, min_nodes=2)
```

## Related Files

- [`../aml/config.py`](../aml/config.py): Shared ML workspace configuration
- [`../aml/provision.py`](../aml/provision.py): Cluster provisioning scripts
- [`../aml/pipeline.py`](../aml/pipeline.py): ML pipeline that benefits from pre-warmed clusters