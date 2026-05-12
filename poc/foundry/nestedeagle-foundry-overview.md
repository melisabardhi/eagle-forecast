# End-to-End Overview: Nested Eagle Publisher Self-Serve Onboarding

## 1. Onboard Publisher (One-Time)

Share publisher details with Microsoft partner POC:
- Publisher name
- Display name
- Description
- Authorized security groups (name + object ID)
- Publisher icon (SVG, light/dark theme, 42x42px, <1KB)

**(Assuming) non-monetized publishing**: Publisher ID and Seller ID are NOT required.
Skip marketplace integration step entirely.

**References:**
- [publisher-self-serve/1.share-publisher-details.md](publisher-self-serve/1.share-publisher-details.md)
- [publisher-self-serve/3.2.manage-publisher-marketplace-integration-details.md](publisher-self-serve/3.2.manage-publisher-marketplace-integration-details.md)

## 2. Package and Register Assets

**Model assets:**
- Checkpoint: `inference-last.ckpt`
- Initial conditions zarr files: `{version}/initial_conditions/{date}/{hour}/hrrr.zarr` + `gfs.zarr`
- Static grid file: `config/hrrr_06km.nc`

**Environment image:**
- Dockerfile with all runtime dependencies pre-installed
- Scoring server logic baked in (no external score.py extension)
- All critical logic contained in image

Register both in Azure ML registry.

**References:**
- [publisher-self-serve/4.0.register-and-upload-model-assets.md](publisher-self-serve/4.0.register-and-upload-model-assets.md)
- [publisher-self-serve/5.1.1.maap-byoc-model-deployment.md](publisher-self-serve/5.1.1.maap-byoc-model-deployment.md)

## 3. Define Runtime Contract with Deployment Template

Create deployment template YAML specifying:
- Scoring port (e.g., 8000)
- Scoring path (e.g., /score)
- Health probe paths and ports
- Allowed instance types
- Model mount path
- Environment variables
- Request timeout, concurrency limits

Deploy template to registry.

**Reference:**
- [publisher-self-serve/5.2.1.maap-deployment-template-creation.md](publisher-self-serve/5.2.1.maap-deployment-template-creation.md)

## 4. Create Release Candidate

Create candidate.yaml with:
- Model asset reference
- Environment asset reference
- Deployment template reference
- SKU for validation
- Inference path and payload (test request)
- Expected response structure

Run CLI: `az ml modelpublisher release-candidate create -p <publisher> -m <model> -f candidate.yaml`

**Reference:**
- [publisher-self-serve/5.1.create-release-candidate-maap.md](publisher-self-serve/5.1.create-release-candidate-maap.md)

## 5. Platform Validates Release Candidate

Automatic validations run:
- **IMAGE_VULNERABILITY**: Container image scan (must be zero critical/high)
- **MAAP_DEPLOYMENT**: Can model deploy to online endpoint
- **MAAP_INFERENCING**: Can endpoint handle inference requests
- **MAAP_BILLING_VALIDATION**: Only for monetized (skip for your case)

Expected timeline: 5–6 days for RC validation.

**Reference:**
- [publisher-self-serve/6.validations.md](publisher-self-serve/6.validations.md)

## 6. Approval and Production Promotion

After successful validation, model enters approval stage automatically.

Microsoft PM approves (required before promotion).

Run: `az ml modelpublisher release-candidate promote-to-prod -p <publisher> -m <model> -v <version>`

Model is now in Azure AI Foundry catalog for consumers.

**References:**
- [publisher-self-serve/7.approval-flow.md](publisher-self-serve/7.approval-flow.md)
- [publisher-self-serve/8.promote-to-production.md](publisher-self-serve/8.promote-to-production.md)

## How Nested Eagle Runs After Published

1. Consumer discovers model in Azure AI Foundry catalog.
2. Clicks Use model and deploys to online endpoint (existing for output of forecast to blob storage). 
3. Endpoint's managed identity is assigned to running container.
4. Consumer calls `/score` endpoint with JSON request containing:
   - `lead_time`: forecast lead time
   - `version`: model version
   - `ic_timestamp`: initialization timestamp (optional; defaults to NRT)
   - `output_storage_account`: consumer's storage account (optional)
   - `output_container`: consumer's blob container (optional)
   - `output_blob_prefix`: subfolder prefix (optional)
5. Scoring server:
   - Resolves mounted model assets at `AZUREML_MODEL_DIR`
   - Calls `prep_config()` with paths to checkpoint and zarr inputs
   - Executes `eagle_inference(config)`
   - If storage provided: uploads results to consumer's blob storage using endpoint's managed identity
   - Returns JSON response with status, metadata, and (optionally) blob URIs
6. Consumer receives response and can retrieve forecast outputs from blob storage.

## Key Design Truths from Documentation

| Aspect | What Docs Say |
|--------|---|
| HTTP framework | No specific framework required; any HTTP server satisfying port/path/probe contract works |
| Port number | Port 8000 is conventional; any port works if deployment template and probes match |
| Deployment model | Only online MaaP endpoints supported in this self-serve flow; batch is not documented |
| Scoring pattern | Long-running HTTP service required (not one-shot script) |
| Secrets management | Use managed identity for blob auth; no credentials in image or request |
| Non-monetized path | Skip marketplace integration, no billing validation, but still complete core publisher + RC workflow |
| Output persistence | Consumer provides storage destination; endpoint doesn't own output storage |