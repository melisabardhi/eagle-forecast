import argparse
import os
import sys
from eagle.tools.inference import main as eagle_inference

import utils
import stac_item
import upload
import postproc


def prep_config(
    ic_timestamp,
    lead_time,
    version,
    checkpoint_path,
):
    init_str = ic_timestamp.strftime("%Y-%m-%dT%H")

    config = {
        "checkpoint_path": f"{checkpoint_path}/inference-last.ckpt",
        "lead_time": lead_time,
        "start_date": init_str,
        "end_date": init_str,
        "freq": "6h",
        "input_dataset_kwargs": {
            "cutout": [
                {
                    "dataset": f"{version}/initial_conditions/{ic_timestamp.strftime('%Y/%m/%d/%H')}/hrrr.zarr",
                    "trim_edge": [25, 24, 25, 26],
                },
                {
                    "dataset": f"{version}/initial_conditions/{ic_timestamp.strftime('%Y/%m/%d/%H')}/gfs.zarr",
                },
            ],
            "adjust": "all",
            "min_distance_km": 6,
        },
        "output_path": f"{version}/inference/{ic_timestamp.strftime('%Y/%m/%d/%H')}",
    }

    return config


def run(
    version,
    lead_time,
    checkpoint_path,
    output_storage_url=None,
    output_storage_account=None,
    output_container=None,
    grid_file="config/hrrr_06km.nc",
):
    ic_timestamp = utils.get_nrt_timestamp()

    os.makedirs(
        f"{version}/inference/{ic_timestamp.strftime('%Y/%m/%d/%H')}", exist_ok=True
    )

    config = prep_config(
        version=version,
        ic_timestamp=ic_timestamp,
        lead_time=lead_time,
        checkpoint_path=checkpoint_path,
    )

    eagle_inference(config)

    # Post-process: split raw forecast into global.nc + conus.nc
    print("Post-processing: splitting into global + CONUS...")
    postproc.postprocess_forecast(version=version, grid_file=grid_file)

    # Generate STAC Items for MPC Pro GeoCatalog ingestion
    # Writes to {version}/stac/items/{folder}/ — separate from data files
    if output_storage_url:
        stac_item.write_stac_items(ic_timestamp, version, output_storage_url)

    # Upload forecast + STAC to blob storage
    if output_storage_account and output_container:
        print("Uploading forecast + STAC to blob storage...")
        upload.upload_forecast(
            version=version,
            storage_account=output_storage_account,
            container=output_container,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config")
    args = parser.parse_args()

    if not args.config:
        print("Example usage:  python inference.py --config config.yaml")
        sys.exit(1)

    config = utils.load_config(args.config)

    lead_time = config["lead_time"]
    version = config["version"]
    checkpoint_path = config["checkpoint_path"]
    output_storage_url = config.get("output_storage_url")
    output_storage_account = config.get("output_storage_account")
    output_container = config.get("output_container", "nested-eagle-forecasts")
    grid_file = config.get("grid_file", "config/hrrr_06km.nc")

    run(
        version=version,
        lead_time=lead_time,
        checkpoint_path=checkpoint_path,
        output_storage_url=output_storage_url,
        output_storage_account=output_storage_account,
        output_container=output_container,
        grid_file=grid_file,
    )
