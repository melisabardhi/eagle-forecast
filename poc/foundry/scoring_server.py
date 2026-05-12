import os
from pathlib import Path
from typing import Optional

import pandas as pd
from azure.identity import ManagedIdentityCredential
from azure.storage.blob import BlobServiceClient
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from eagle.tools.inference import main as eagle_inference
from inference import prep_config

app = FastAPI(title="nested-eagle-scoring")


class ScoreRequest(BaseModel):
    lead_time: int = Field(default=240, ge=1)
    version: Optional[str] = None
    ic_timestamp: Optional[str] = None
    output_subdir: Optional[str] = None
    output_storage_account: Optional[str] = None  # e.g. "mystorageaccount"
    output_container: Optional[str] = None        # e.g. "nested-eagle-forecasts"
    output_blob_prefix: Optional[str] = None      # optional subfolder within container


def resolve_ic_timestamp(raw_ts: Optional[str], freq: str) -> pd.Timestamp:
    if raw_ts:
        ts = pd.Timestamp(raw_ts)
        if ts.tz is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        return ts
    return pd.Timestamp.now(tz="UTC").floor(freq) - pd.Timedelta(freq)


def upload_to_blob(
    local_path: str,
    storage_account: str,
    container: str,
    blob_prefix: str,
) -> list[str]:
    """Upload all files under local_path to blob storage using managed identity."""
    account_url = f"https://{storage_account}.blob.core.windows.net"
    credential = ManagedIdentityCredential()
    client = BlobServiceClient(account_url=account_url, credential=credential)
    container_client = client.get_container_client(container)

    uploaded = []
    for file_path in Path(local_path).rglob("*"):
        if file_path.is_file():
            relative = file_path.relative_to(local_path)
            blob_name = f"{blob_prefix}/{relative}" if blob_prefix else str(relative)
            with open(file_path, "rb") as f:
                container_client.upload_blob(name=blob_name, data=f, overwrite=True)
            uploaded.append(f"{account_url}/{container}/{blob_name}")

    return uploaded


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/score")
def score(req: ScoreRequest):
    model_dir = os.getenv("AZUREML_MODEL_DIR")
    if not model_dir:
        raise HTTPException(status_code=500, detail="AZUREML_MODEL_DIR is not set")

    version = req.version or os.getenv("DEFAULT_VERSION", "nested_eagle")
    freq = os.getenv("DEFAULT_FREQ", "6h")
    output_root = os.getenv("OUTPUT_ROOT", "/tmp/nested-eagle-output")

    ic_ts = resolve_ic_timestamp(req.ic_timestamp, freq)

    if req.output_subdir:
        final_output_path = str(Path(output_root) / req.output_subdir)
    else:
        final_output_path = str(
            Path(output_root) / version / "inference" / ic_ts.strftime("%Y/%m/%d/%H")
        )

    Path(final_output_path).mkdir(parents=True, exist_ok=True)

    # model_dir is the root for both checkpoint and input zarr assets
    config = prep_config(
        ic_timestamp=ic_ts,
        lead_time=req.lead_time,
        version=version,
        checkpoint_path=model_dir,
        input_path=model_dir,
        output_path=final_output_path,
    )

    try:
        eagle_inference(config)
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"inference failed: {ex}")

    # Upload to caller-supplied blob storage if provided
    blob_uris = []
    if req.output_storage_account and req.output_container:
        blob_prefix = req.output_blob_prefix or (
            f"{version}/inference/{ic_ts.strftime('%Y/%m/%d/%H')}"
        )
        try:
            blob_uris = upload_to_blob(
                local_path=final_output_path,
                storage_account=req.output_storage_account,
                container=req.output_container,
                blob_prefix=blob_prefix,
            )
        except Exception as ex:
            raise HTTPException(status_code=500, detail=f"upload failed: {ex}")

    return {
        "status": "ok",
        "version": version,
        "lead_time": req.lead_time,
        "ic_timestamp_utc": ic_ts.isoformat(),
        "output_path": final_output_path if not blob_uris else None,
        "output_blobs": blob_uris or None,
    }