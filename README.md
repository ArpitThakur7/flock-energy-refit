# REFIT data cleaning and washing-machine disaggregation

A Flock Energy take-home on the REFIT Electrical Load Measurements dataset (20 UK homes, 2013–2015). It is a small, reproducible pipeline that:

1. **Cleans raw House 1 data** to 1-minute resolution, fixing a daylight-saving error in the raw timestamps, merging overlapping files, removing sensor error codes and duplicates, and flagging outages. The result matches the official cleaned data with correlation 0.997.
2. **Analyses washing-machine use** in 12 homes from the official cleaned data: 4,566 detected cycles, usage by hour and weekday, and cycle duration, energy and peak compared across homes.
3. **Estimates washing-machine power from the whole-house meter** with a seq2point-style XGBoost model. It is validated leave-one-house-out against two baselines. On homes it has never seen, it finds 81% of washes and cuts daily energy error by 28% compared with predicting zero.

| Document | Contents |
|---|---|
| [DATA.md](DATA.md) | Raw data coverage and quality findings, cleaning steps, gap and outlier decisions, remaining concerns |
| [RESULTS.md](RESULTS.md) | Washing-machine EDA, plots, model results, validation, failure analysis, cited papers |
| [Recommendation.md](Recommendation.md) | One-page utility summary and the Section 4 answers |

## Setup and run

Requires Python 3.10+ (tested on 3.13, Windows 11) and roughly 12 GB of free disk space for the extracted csvs.

```bash
pip install -r requirements.txt
python run_all.py
```

`run_all.py` runs these scripts in order (each can also be run alone from `src/`):

| Step | Script | Output |
|---|---|---|
| Data | `src/get_data.py` | Downloads the two `.7z` archives (~1.2 GB) and extracts only the files used into `data/raw` and `data/clean`. If you already have the `CLEAN_House*.csv` files, put them in `data/clean/` and they are reused. |
| Part 1 | `src/part1_clean_raw.py` | `data/interim/raw_h1_cleaned_1min.parquet`, `outputs/raw_h1_*.csv`, `figures/p1_*.png` |
| Part 2 | `src/part2_wm_eda.py` | `outputs/wm_quality.csv`, `wm_cycles.csv`, `wm_cycle_summary.csv`, `figures/p2_*.png` |
| Part 3 | `src/part3_model.py` | `outputs/model_metrics*.csv`, `model_daily_energy.csv`, `model_feature_importance.csv`, `figures/p3_*.png` |
| Ablation | `REFIT_NO_TIME=1 python src/part3_model.py` | `outputs/*_notime.csv` (model without time-of-day features) |

The full run takes about 5 minutes on a laptop. XGBoost uses the GPU if one is available and falls back to the CPU otherwise. Seeds are fixed (`SEED = 42`). GPU training can still vary in the last decimal place.

> The download links in the brief (`pureportal.strath.ac.uk/files/...`) return HTTP 403. `get_data.py` uses the equivalent `pure.strath.ac.uk/ws/portalfiles/portal/...` links.

### Repository layout

```
src/config.py         every path, house selection and threshold in one place
src/clean_data.py     load an official cleaned csv -> 1-minute parquet cache
src/cycles.py         washing-machine cycle rule (used for EDA and model filtering)
src/part1_clean_raw.py, part2_wm_eda.py, part3_model.py, get_data.py
run_all.py            end-to-end runner
figures/  outputs/    generated plots and tables (committed so results are viewable)
data/                 not committed (downloaded by get_data.py)
```

## Key assumptions and preprocessing decisions

* **Clock.** The `Unix` column is the clock. Raw Part1 is converted from UK local time to UTC (DATA.md explains the evidence). All resampling is done in UTC to avoid daylight-saving duplicates, and local time is used only for hour-of-day analysis.
* **1-minute resampling** uses the **mean** of the samples in each minute, so energy totals are kept. A minute with no samples stays **NaN**.
* **Gaps:** gaps of 5 minutes or less are forward-filled. Longer gaps are flagged and never filled.
* **Invalid values:** IAM > 4 kW, aggregate > 15 kW, negative values, and any appliance reading above the whole-house reading. These become **NaN, not 0**, so they are not mistaken for "off".
* **Duplicates:** exact duplicate rows are dropped. Rows that share a timestamp but differ are merged, keeping the last non-missing value per column.
* **Washing-machine target:** the readme's washing-machine channel. House 4 has two washing machines, so its target is their sum.
* **The REFIT `Issues` flag is not used to drop data.** It fires on 17–47% of the minutes when the washing machine is running, so dropping those minutes would remove the events being modelled. Only minutes where the washing machine itself exceeds the aggregate are excluded.
* **Cycle rule:** above 20 W counts as running; pauses of 15 minutes or less are bridged; a cycle needs at least 10 minutes, 0.05 kWh and a 200 W peak.

## Validation design

**Leave-one-house-out over 12 homes.** Each home is the test home once and is never used for training, early stopping or threshold selection in that fold. Inside the training homes, the last 20% of each home's timeline (by time) is used for early stopping. Overlapping 61-minute windows therefore cannot leak between train and test, and the test mimics the real use case: a new customer with no sub-metering. The baselines are always-off and an hour-of-week usage profile.

## Trade-offs

* **XGBoost on window features instead of a CNN (Seq2Point).** It is much faster to train 12 folds, easier to explain and inspect (feature importance, ablation), and good enough to clearly beat the baselines. The cost is that hand-made features probably capture the low motor tail less well than a CNN would.
* **Imbalance handling.** Every minute near a cycle is kept, plus a 10% sample of other minutes with a weight of 10. This keeps training at about 1.1 M rows per fold without biasing the loss.
* **Cycle filter after prediction.** It removes short false alarms and makes total energy much less biased, at the cost of some recall on unusual machines (House 19).
* **Metrics.** Headline metrics are daily-energy and cycle-level, because per-minute MAE rewards predicting zero for an appliance that is off more than 90% of the time. MAE is still reported.
* **House choice.** 12 of 20 homes are used. Homes with an ambiguous or changing washing-machine channel (6, 8, 9, 10, 11, 12, 13, 20) were left out rather than guessed at.

## AI tools used

I wrote this repository with the help of **Claude (Anthropic) in Claude Code**, used as a pair programmer. It helped to:
* find a working download path for the data;
* write and debug the pipeline code;
* investigate data issues: it ran the checks that revealed the Part1 local-time offset, the power-of-two glitch values, and the bias in the `Issues` flag;
* draft the markdown documents.

All decisions, numbers and plots were checked against the pipeline's actual outputs. Every figure and table in the docs is produced by the code in this repo.

## Possible improvements

1. A second-stage, event-level classifier that confirms predicted cycles, to reduce false alarms (currently ~61% of predicted washes).
2. A Seq2Point CNN under the same leave-one-house-out folds, for comparison.
3. More homes after manual channel checks, plus per-home adaptation from a few labelled washes or user feedback.
4. Prediction intervals for monthly washing-machine kWh, so customer-facing insights can be held back when uncertain.
5. Unit tests for the cycle rule and the timezone conversion. These are checked indirectly today, through the official-data comparison and the plots.

## Data licence and citation

REFIT data © University of Strathclyde, CC-BY 4.0. Murray, D., Stankovic, L. & Stankovic, V. *An electrical load measurements dataset of United Kingdom households from a two-year longitudinal study.* Scientific Data 4, 160122 (2017).
