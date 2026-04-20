<!-- DO NOT CHANGE MARKDOWN HEADERS. IF CHANGED, MODEL CARD MAY BE REJECTED BY A REVIEWER -->

## Intended Use

### Primary Use Cases

Nested-EAGLE is designed for operational and research weather forecasting applications, specifically targeting near-real-time environmental prediction over the contiguous United States (CONUS). The model is intended for use by meteorologists, atmospheric scientists, emergency managers, and developers building weather-informed applications.

1. **Operational near-real-time forecasting:** Generating 240-hour (10-day) atmospheric forecasts every 6 hours, aligned with GFS/HRRR initialization cycles, for dissemination through the Microsoft Planetary Computer.
2. **High-resolution regional prediction:** Providing 6 km CONUS-scale forecasts by nesting a regional HRRR grid inside a global GFS grid — capturing mesoscale weather features that global-only models miss.
3. **Research and model comparison:** Enabling atmospheric scientists to compare AI-based forecasting against operational NWP baselines (GFS, ECMWF HRES) using publicly accessible output via the Planetary Computer STAC catalog.
4. **Downstream application development:** Serving as a data source for derivative products such as renewable energy forecasting, agricultural weather services, and emergency management decision support.

### Out-of-Scope Use Cases

Nested-EAGLE is not designed for the following and should not be used in these contexts without additional validation:

- **Safety-critical aviation or maritime routing decisions** without human expert review — the model is a research-grade AI forecast, not a certified operational product.
- **Sub-hourly or convection-permitting forecasting** — the model operates at 6-hour temporal resolution and 6 km spatial resolution; it is not a convection-allowing model and is not designed for severe storm nowcasting.
- **Forecasts outside the CONUS domain at high resolution** — the nested HRRR grid is CONUS-only; global output inherits GFS resolution (0.25°).
- **Direct public emergency alerts** — model output should be reviewed and interpreted by qualified meteorologists before informing public safety decisions.

## Responsible AI Considerations

Nested-EAGLE is a physics-informed AI weather forecasting model, not a generative language model. The primary responsible AI considerations are centered on scientific accuracy, uncertainty communication, and appropriate use:

- **Forecast uncertainty:** Like all NWP and AI weather models, Nested-EAGLE produces deterministic point forecasts. Users should be aware that forecast skill degrades with lead time, and uncertainty grows particularly beyond Day 5. Single-model deterministic output should not be treated as ground truth.
- **Domain boundaries:** The model is trained and validated on CONUS meteorological conditions. Performance at domain edges (coastal boundaries, terrain transitions) may be degraded relative to the interior domain.
- **Training data representation:** Model skill may vary by season, weather regime, and geographic subregion. Performance over complex terrain (Rockies, Cascades, Appalachians) and coastal zones should be independently validated.
- **No sensitive use case:** This model does not make decisions about individuals and does not affect legal status, healthcare, employment, education, welfare, or financial services. It is a scientific forecasting tool.
- **Output interpretation:** End users — particularly non-meteorologists — should use model output through interpreted products rather than raw model fields. Raw NetCDF output requires domain expertise to interpret correctly.

## Training Data

Nested-EAGLE is built on the **ECMWF Anemoi framework** and trained using reanalysis and operational NWP data:

1. **Initial conditions:** Global Forecast System (GFS) at 0.25° resolution (via NOAA Open Data Dissemination / Planetary Computer) and High-Resolution Rapid Refresh (HRRR) at 3 km resolution (regridded to 6 km for the nested cutout).
2. **Model architecture:** Anemoi graph neural network with Flash Attention, trained for autoregressive rollout at 6-hour intervals.
3. **Checkpoint:** `inference-last.ckpt` stored in Azure Blob Storage (`eagle-checkpoints` container), representing the production inference checkpoint. Checkpoint size is >1 GB.
4. **Framework license:** The Anemoi framework is open source under **Apache 2.0**. The model weights are publicly available on GitHub. Formal open source licensing for the weights is pending confirmation from NOAA.

*For full training methodology and hyperparameter details, refer to the ECMWF Anemoi documentation and the NOAA EPIC team's technical report (forthcoming).*
