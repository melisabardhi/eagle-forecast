## Required model metadata

**Publisher:** National Oceanic and Atmospheric Administration (NOAA)  
**Prepared for:** Microsoft Azure AI Foundry onboarding  

---

1. **Model name as used in marketing:**  
   Nested-EAGLE

2. **Model name without a blank space:**  
   Nested-EAGLE

3. **Short description of the model:**  
   Nested-EAGLE is a NOAA AI weather forecasting model built on the ECMWF Anemoi framework that produces 240-hour (10-day) near-real-time atmospheric forecasts for CONUS at 6 km resolution by nesting a high-resolution HRRR grid inside a global GFS grid.

4. **Does this model support finetuning?**  
   N

5. **Target release date:**  
   TBD

6. **Releasing Model for Public Preview or General Availability:**  
   Public Preview

7. **License:**  
   Apache 2.0

8. **License description:**  
   The Anemoi framework used to build Nested-EAGLE is licensed under [Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0). The model weights are publicly available on GitHub under Apache 2.0. The full license text is included in this folder (`apache-2.0-license.md`) for review — please confirm the terms are correct and convert to PDF for submission to Microsoft.

9. **Inference task types:**  
   Forecasting

10. **Minimum Recommended VM SKU:**  
    Standard_NC40ads_H100_v5

11. **Inference Recommended VM SKU:**  
    Standard_NC40ads_H100_v5

12. **Keywords (up to 3 from approved list):**  
    Reasoning, Understanding, Multipurpose

13. **Modality Input:**  
    Meteorological gridded data (NetCDF / Zarr) — GFS global (0.25°) + HRRR CONUS (3 km, regridded to 6 km)

14. **Modality Output:**  
    Meteorological gridded data (NetCDF) — 14 atmospheric variables × 12 pressure levels + surface fields, 240-hour forecast at 6-hour intervals

15. **Languages Supported:**  
    N/A (scientific forecasting model, not a language model)

16. **Sample prompt:**  
    ```
    Input: GFS global analysis (t=00Z) + HRRR CONUS analysis (t=00Z) as Zarr arrays
    Task: Generate 240-hour (40-step) autoregressive atmospheric forecast for CONUS at 6 km resolution
    Output: NetCDF file containing forecasted fields (temperature, wind, geopotential, humidity, precipitation) at 6-hour intervals from t+6h to t+240h
    ```

17. **Sample API response:**  
    ```
    {
      "forecast_cycle": "2026-04-20T00:00:00Z",
      "lead_times_hours": [6, 12, 18, ..., 240],
      "variables": ["t2m", "u10", "v10", "z500", "t850", "q700", ...],
      "grid": "HRRR-nested 6km CONUS + GFS 0.25deg global",
      "output_format": "NetCDF4",
      "output_location": "https://<mpc-blob>.blob.core.windows.net/nested-eagle-forecasts/v1/2026/04/20/00/forecast.nc",
      "planetary_computer_stac": "https://planetarycomputer.microsoft.com/api/stac/v1/collections/noaa-nested-eagle"
    }
    ```

18. **Model announcement title (max 25 characters):**  
    Nested-EAGLE

19. **Logo:**  
    To be provided by NOAA EPIC team in SVG format (42×42 px, dark background + light background versions). *(Pending — not blocking for Preview launch)*


