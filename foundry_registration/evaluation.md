<!-- DO NOT CHANGE MARKDOWN HEADERS. IF CHANGED, MODEL CARD MAY BE REJECTED BY A REVIEWER -->

Nested-EAGLE is evaluated against operational numerical weather prediction baselines — specifically ECMWF HRES and GFS — using standard meteorological skill metrics (RMSE, ACC) on held-out forecast cycles. Verification is performed against ERA5 reanalysis as ground truth. Evaluation focuses on CONUS regional skill given the model's nested high-resolution HRRR grid, with particular attention to 2-meter temperature, 10-meter wind speed, 500 hPa geopotential height, and total precipitation across lead times out to 240 hours (10 days).

| Category | Metric | Nested-EAGLE | GFS (Operational) | ECMWF HRES |
|---|---|---|---|---|
| Upper air skill | 500 hPa Z ACC (Day 5) | TBD | TBD | TBD |
| | 500 hPa Z RMSE (Day 5) | TBD | TBD | TBD |
| Surface temperature | 2m Temp RMSE (Day 3, CONUS) | TBD | TBD | TBD |
| Wind | 10m Wind Speed RMSE (Day 3) | TBD | TBD | TBD |
| Precipitation | 24h Precip ETS (Day 1-3) | TBD | TBD | TBD |
| Overall | S1 Score (500 hPa, Day 5) | TBD | TBD | TBD |

*Evaluation will be conducted over a retrospective period using operational GFS/HRRR initial conditions. Full verification statistics and methodology will be documented in the NOAA model card supplement prior to launch.*
