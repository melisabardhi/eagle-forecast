FROM mcr.microsoft.com/azureml/openmpi4.1.0-cuda12.1-cudnn8-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip setuptools wheel

# Core runtime deps from customer POC
RUN python -m pip install \
    ufs2arco \
    anemoi-datasets==0.5.30 \
    anemoi-graphs==0.8.2 \
    anemoi-models==0.11.3 \
    anemoi-transform==0.1.21 \
    anemoi-utils==0.4.42 \
    anemoi-inference==0.9.1 \
    "torch<2.7" \
    eagle-tools

RUN python -m pip install "flash-attn<2.8" --no-build-isolation --no-cache-dir

# HTTP scoring server + Azure Blob upload via Managed Identity
RUN python -m pip install \
    fastapi \
    uvicorn \
    pydantic \
    pandas \
    pyyaml \
    azure-identity \
    azure-storage-blob

# Inference and scoring files
COPY inference.py /app/inference.py
COPY utils.py /app/utils.py
COPY scoring_server.py /app/scoring_server.py

# Keep these only if inference.py imports them at module load time
COPY stac_item.py /app/stac_item.py
COPY upload.py /app/upload.py
COPY postproc.py /app/postproc.py
COPY ingest.py /app/ingest.py

ENV ENGINE_STARTUP_PORT=8000
ENV DEFAULT_VERSION=nested_eagle
ENV DEFAULT_FREQ=6h
ENV OUTPUT_ROOT=/tmp/nested-eagle-output

EXPOSE 8000

CMD ["uvicorn", "scoring_server:app", "--host", "0.0.0.0", "--port", "8000"]