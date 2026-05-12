# Detailed Instructions: Publish Nested Eagle to Azure AI Foundry with Publisher Self-Serve (BYOC, Non-Monetized)

## Goal

Publish Nested Eagle as a non-monetized model through publisher self-serve so consumers can deploy it as an online endpoint and run inference through an HTTP scoring path.

This guide assumes:
- You are using BYOC.
- You are not enabling monetization.
- Model assets include checkpoint and zarr inputs.
- Your scoring service calls `prep_config` and eagle inference.

## Phase 1: Publisher Prerequisites

### Step 1. Confirm whether publisher onboarding is already completed
1. If your publisher has already been onboarded previously, skip this step and continue to CLI setup.
2. If not onboarded, share publisher details with your Microsoft partner POC.

### Step 2. Provide required publisher details
1. Provide Publisher Name.
2. Provide Display Name.
3. Provide Description.
4. Provide Authorized Security Group name and object ID.
5. Provide Publisher icon assets as specified.

For non-monetized onboarding:
1. Publisher ID is not required.
2. Seller ID is not required.

### Step 3. Skip marketplace integration
1. Do not run marketplace integration steps.
2. Do not configure offer or plan information.

## Phase 2: Prepare BYOC Runtime

### Step 4. Build the scoring container
1. Create a Dockerfile that installs all required runtime dependencies at build time.
2. Include inference runtime dependencies.
3. Include HTTP server dependencies.
4. Include Azure storage SDK dependencies if you will upload outputs to consumer storage.
5. Copy scoring service and inference modules into the image.
6. Start a long-running scoring process through `CMD` or `ENTRYPOINT`.

BYOC rules:
1. No external scoring extension files for critical logic.
2. Do not rely on runtime package downloads.
3. Keep startup deterministic.

### Step 5. Implement scoring API contract
1. Implement health endpoint for liveness and readiness.
2. Implement scoring endpoint for inference requests.
3. Read mounted model root from `AZUREML_MODEL_DIR`.
4. Build inference config through `prep_config`.
5. Execute eagle inference.
6. Return JSON response with status and output metadata.
7. If storage destination is provided by caller, upload outputs and return blob URLs.

Important:
1. Online endpoints require a long-running HTTP process.
2. One-shot script execution alone is not sufficient for MaaP online validation.

### Step 6. Align model asset path assumptions
1. Ensure checkpoint and zarr folders are uploaded in a structure expected by `prep_config`.
2. Pass the mounted model root as checkpoint base and input base according to your `prep_config` signature.
3. Verify path resolution before RC submission with a local container test.

## Phase 3: Register Assets

### Step 7. Register model asset
1. Package checkpoint and zarr input hierarchy.
2. Include any required static file assets.
3. Create model as `custom_model` with required properties.
4. Register model directly in registry as required by docs.

### Step 8. Register environment asset
1. Build environment image from Dockerfile.
2. Create environment in workspace.
3. Share environment to registry.

## Phase 4: Define Deployment Contract

### Step 9. Create deployment template YAML
1. Set `deployment_template_type` to `online`.
2. Set environment reference to registered environment.
3. Set `AZUREML_MODEL_DIR` to the full mounted model directory.
4. Set `scoring_port` to match your server port.
5. Set `scoring_path` to match your scoring route.
6. Configure liveness and readiness probes to match health route and port.
7. Set `allowed_instance_types`.
8. Set `default_instance_type` and `instance_count`.
9. Set request timeout and concurrency limits.

### Step 10. Create deployment template in registry
1. Run deployment-template create command with your YAML file.
2. Save template name and version for release candidate usage.

## Phase 5: Release Candidate

### Step 11. Create candidate YAML
1. Set `modelAssetReference`.
2. Set `deploymentTemplateReference`.
3. Set `deploymentType` to `MaaP`.
4. Set `sku` or `skus`.
5. Set `inferencePath` matching scoring path.
6. Set `inferencePayload` for test request.
7. Optionally set `inferenceResponse` structure.
8. Do not include monetization fields.

### Step 12. Create release candidate
1. Run release-candidate create command with candidate YAML.
2. Record candidate version and validation IDs.

## Phase 6: Validation and Remediation

### Step 13. Monitor validation status
1. Check release candidate status via show command.
2. Download validation results by validation ID.
3. Review deployment logs, inferencing logs, and vulnerability results.

### Step 14. Resolve failures if any
1. Deployment failures: fix startup process, probe path, probe port, scoring path, scoring port, or asset mounts.
2. Inferencing failures: fix request schema, path handling, config building, or output handling.
3. Vulnerability failures: patch image and rebuild environment.
4. Recreate RC with incremented version after fixes.

## Phase 7: Approval and Production

### Step 15. Wait for approval
1. After validations pass, model enters Approval stage.
2. Coordinate with Microsoft PM for required approval.

### Step 16. Promote approved release candidate
1. Run promote-to-prod command for approved version.
2. Track status until promotion completes.

## Phase 8: Consumer Runtime Pattern

### Step 17. Consumer deployment behavior
1. Consumer chooses model from catalog and deploys to new or existing endpoint.
2. Endpoint managed identity is used by container at runtime.
3. If caller passes storage account and container in request, service uploads outputs to consumer storage.
4. Caller receives JSON with status and output locations.

### Step 18. Access control for storage upload
1. Consumer grants endpoint managed identity permission on their target container.
2. No secrets are required in image or request when managed identity is used.

## Operational Checklist Before First RC

1. Scoring path in server and deployment template are identical.
2. Server port, scoring_port, and probe ports are identical.
3. Health route exists and matches probe paths.
4. `AZUREML_MODEL_DIR` points to actual mounted model root.
5. `prep_config` path assumptions match registered asset structure.
6. Non-monetized candidate excludes monetization fields.
7. Image scan is clean for critical and high issues.
8. Test inference request succeeds locally in container and in pre-RC endpoint test.

## Included vs Excluded Scope

Included:
1. BYOC container build.
2. Online scoring API contract.
3. Model and environment registration.
4. Deployment template and RC flow.
5. Validation, approval, and promotion.

Excluded:
1. Marketplace monetization setup.
2. Billing validation requirements.
3. Batch endpoint workflow.
4. Post-processing or downstream business pipeline beyond endpoint inference contract.S