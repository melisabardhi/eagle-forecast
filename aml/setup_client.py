"""
Nested-EAGLE: AML Workspace Connection Test

Run this script to verify VS Code + Azure ML SDK is set up correctly.
Prerequisites:
  1. az login (signed in to correct Azure account)
  2. pip install azure-ai-ml azure-identity
  3. Fill in aml/config.py with workspace details
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from config import get_ml_client, SUBSCRIPTION_ID

ml_client = get_ml_client()

# Quick test — should print workspace info
ws = ml_client.workspaces.get(ml_client.workspace_name)
print(f"Connected to workspace: {ws.name}")
print(f"  Region:         {ws.location}")
print(f"  Resource group: {ws.resource_group}")
print(f"  Subscription:   {SUBSCRIPTION_ID}")
print()

# Check existing compute clusters
computes = ml_client.compute.list()
print("Existing compute clusters:")
for c in computes:
    print(f"  - {c.name} ({c.type}, size={getattr(c, 'size', 'N/A')})")
print()
print("Connection verified. Next step: python aml/provision.py")
