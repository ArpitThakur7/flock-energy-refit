# REFIT data cleaning and washing-machine disaggregation

This is my submission for the Flock Energy data science take-home. It works with the REFIT dataset (20 UK homes, 2013 to 2015) and does three things:

1. Cleans the raw House 1 data and resamples it to 1-minute resolution. The trickiest part turned out to be a daylight-saving bug in the raw timestamps. After fixing it, my cleaned series matches the official cleaned data with a correlation of 0.997.
2. Looks at how washing machines are used across 12 homes, using the official cleaned data. I found 4,566 wash cycles and compared when people wash, how long a cycle takes and how much energy it uses.
3. Estimates washing-machine power from the whole-house meter alone. On homes the model has never seen, it picks up about 8 in 10 washes and gets daily washing-machine energy 28% closer than simply guessing zero.

The write-ups are split into three files:

- [DATA.md](DATA.md): what the raw data looks like, what was wrong with it, and how I cleaned it
- [RESULTS.md](RESULTS.md): the washing-machine analysis, the model, how I validated it, and where it fails
- [Recommendation.md](Recommendation.md): a one-page summary for a utility, plus my answers to the Section 4 questions

There is also `Flock_Energy_REFIT_submission.pdf`, which is the same four documents in one file.

## Dataset

The data is not stored in this repo (the extracted csvs are around 12 GB). It is the **REFIT Electrical Load Measurements** dataset from the University of Strathclyde, released under CC-BY 4.0.

- Dataset page: https://pureportal.strath.ac.uk/en/datasets/refit-electrical-load-measurements/
- Raw data (.7z, ~700 MB): https://pure.strath.ac.uk/ws/portalfiles/portal/62090177/REFIT_RAW_081116.7z
- Cleaned data (.7z, ~500 MB): https://pure.strath.ac.uk/ws/portalfiles/portal/62090184/CLEAN_REFIT_081116.7z
- Cleaned data readme: https://pure.strath.ac.uk/ws/portalfiles/portal/62090183/CLEAN_READ_ME_081116.txt

A note on the links: the `pureportal.strath.ac.uk/files/...` addresses given in the brief returned "403 Forbidden" when I tried them, but the same files download fine from the `pure.strath.ac.uk/ws/portalfiles/...` addresses above. You don't need to fetch anything by hand, though. `src/get_data.py` downloads both archives and pulls out only the files the analysis uses. If you already have the `CLEAN_House*.csv` files, drop them into `data/clean/` and it will use those instead.

Files used:

- Part 1: `RAW_House1_Part1.csv` and `RAW_House1_Part2.csv`
- Parts 2 and 3: `CLEAN_House{1,2,3,4,5,7,15,16,17,18,19,21}.csv`

## How to run it

You need Python 3.10 or newer (I used 3.13 on Windows 11) and about 12 GB of free disk space.

```bash
pip install -r requirements.txt
python run_all.py
```

That one command downloads the data if it isn't there yet and then runs every step. It takes about 5 minutes on my laptop. XGBoost will use a GPU if it finds one and falls back to the CPU otherwise. The random seed is fixed, though GPU training can still differ in the last decimal place.

You can also run the steps one by one from inside `src/`:

| Step | Script | What it produces |
|---|---|---|
| Get data | `get_data.py` | `data/raw/` and `data/clean/` |
| Part 1 | `part1_clean_raw.py` | the cleaned House 1 series, `outputs/raw_h1_*.csv`, `figures/p1_*.png` |
| Part 2 | `part2_wm_eda.py` | `outputs/wm_*.csv`, `figures/p2_*.png` |
| Part 3 | `part3_model.py` | `outputs/model_*.csv`, `figures/p3_*.png` |
| Ablation | `REFIT_NO_TIME=1 python part3_model.py` | the same model without time-of-day features, saved as `outputs/*_notime.csv` |
| PDF | `python tools/build_report_pdf.py --repo-url <url>` | rebuilds the submission PDF (needs Edge or Chrome) |

How the code is laid out:

```
src/config.py          paths, house choices and every threshold, all in one place
src/clean_data.py      loads an official cleaned csv and turns it into a 1-minute cache
src/cycles.py          the rule for spotting a washing-machine cycle
src/part1_clean_raw.py, part2_wm_eda.py, part3_model.py, get_data.py
run_all.py             runs everything in order
figures/, outputs/     plots and tables, committed so you can see results without running anything
```

## Main decisions and assumptions

**Timestamps.** I treat the `Unix` column as the clock. The older raw file turned out to store UK local time as if it were UTC, so I convert it (DATA.md explains how I worked that out). All resampling happens in UTC, and I only switch to local time when looking at what hour people wash.

**Resampling.** Each 1-minute value is the average of the readings inside that minute. Averaging power keeps energy totals correct. If a minute has no readings at all, it stays empty rather than being filled in.

**Gaps.** Gaps of up to 5 minutes get filled with the last known value. Anything longer is flagged as an outage and left empty, because I don't think it's defensible to invent hours or days of appliance use.

**Bad values.** Readings that can't be real are set to missing, not to zero: plug sensors above 4 kW, whole-house readings above 15 kW, negative numbers, and any appliance drawing more than the entire house. Setting them to zero would make them look like "appliance off".

**Duplicates.** Exact duplicate rows are dropped. When several rows share a timestamp but disagree, I keep the most recent non-missing value for each column.

**What counts as the washing machine.** I use the channel the readme labels as the washing machine. House 4 has two washing machines, so there I add them together.

**I didn't use the dataset's own "Issues" flag to drop data.** It sounds sensible, but it turns out to fire on 17 to 47% of the minutes when a washing machine is running. Dropping those minutes would throw away a big share of the washes I'm trying to model. Instead I only drop minutes where the washing machine alone reads higher than the whole house.

**What counts as a wash.** The machine counts as running above 20 W. Pauses of up to 15 minutes are bridged, and a cycle has to last at least 10 minutes, use at least 0.05 kWh and peak above 200 W.

## How I validated the model

I used leave-one-house-out testing over all 12 homes. Each home takes a turn as the test home. While it's the test home, it plays no part in training, early stopping or picking any threshold. Inside the training homes, I hold back the last 20% of each home's timeline for early stopping.

The reason for doing it this way: neighbouring 1-minute windows overlap almost completely, so a random split would leak nearly identical data into the test set and make the model look far better than it is. Testing on a home the model has never seen is also the honest version of the real use case, which is a new customer with no appliance-level metering. I compare against two baselines: predicting "off" all the time, and a typical hour-of-week usage profile.

## Trade-offs I made

- I used XGBoost on hand-made window features rather than a neural network like Seq2Point. It trains 12 folds in a few minutes, it's easy to inspect, and it already beats both baselines clearly. The cost is that it probably captures the quiet tail end of a wash less well than a CNN would.
- The washing machine is off over 90% of the time, so I keep every minute near a real wash and a random 10% of the rest, giving those a weight of 10. That keeps training to about a million rows per fold without biasing the model.
- After predicting, I keep only predictions that look like a complete wash (same rule as above). This removes a lot of short false alarms and makes the energy estimate much less biased, but it costs some detection on one unusual machine (House 19).
- My headline metrics are daily energy and per-cycle detection, not per-minute error. Per-minute error rewards predicting zero for an appliance that's almost always off, so I report it but don't lean on it.
- I used 12 of the 20 homes. The other eight have a washing-machine channel that is missing, unclear or changes during the study, and I'd rather leave them out than guess.

## AI tools used

I used Claude (Anthropic's assistant, through Claude Code) as a coding partner on this project. It helped me get the data downloading when the official links failed, write and debug the scripts, run the checks that turned up the timestamp bug, the odd sensor values and the problem with the "Issues" flag, and draft the documents. I went through the outputs and decisions myself, and every number and plot in the write-ups comes straight from the code in this repo.

## What I'd improve with more time

1. Add a second step that looks at each predicted wash as a whole and decides whether it's real. False alarms are the model's biggest weakness right now, with about 6 in 10 predicted washes being something else.
2. Try a Seq2Point neural network on the same folds and compare.
3. Add more homes once I've checked their channel labels by hand, and let the model adapt to a new home from a few confirmed washes.
4. Give a range instead of a single number for monthly washing-machine energy, so an insight is only shown to a customer when the model is confident.
5. Add unit tests for the cycle rule and the timezone conversion. At the moment they're only checked indirectly, through the comparison with the official data and the plots.

## Citation

REFIT data © University of Strathclyde, CC-BY 4.0. Murray, D., Stankovic, L. and Stankovic, V. (2017). An electrical load measurements dataset of United Kingdom households from a two-year longitudinal study. *Scientific Data* 4, 160122.
