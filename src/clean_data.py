"""Loading the official cleaned REFIT files and resampling them to 1 minute.

The cleaned csvs have columns
    Time, Unix, Aggregate, Appliance1..Appliance9, Issues
at an irregular ~8 s cadence, with short NaNs already forward-filled by the
REFIT team. Long outages simply have no rows.

Resampling rule: mean of all samples that fall in each UTC minute. The mean of
power over the minute is proportional to the energy used in that minute, so the
1-minute series keeps kWh totals. Minutes with no samples stay NaN, so outages
are not silently filled. Resampling is done on the UTC Unix timestamp (no DST
ambiguity); a local-time index is only added for hour-of-day analysis.
"""
import pandas as pd

from config import CLEAN_DIR, INTERIM, LOCAL_TZ, WM_CHANNEL


def clean_csv_path(house: int):
    matches = sorted(CLEAN_DIR.rglob(f"CLEAN_House{house}.csv"))
    if not matches:
        raise FileNotFoundError(
            f"CLEAN_House{house}.csv not found under {CLEAN_DIR}; run src/get_data.py")
    return matches[0]


def load_wm_house(house: int, refresh: bool = False) -> pd.DataFrame:
    """1-minute aggregate + washing machine + issues flag for one house.

    Returns a DataFrame indexed by UTC minute with columns
    aggregate, wm (W, float32), issues (fraction of samples flagged, 0-1)
    and n_samples (raw samples in that minute; 0 => missing minute).
    """
    cache = INTERIM / f"clean_h{house}_1min.parquet"
    if cache.exists() and not refresh:
        return pd.read_parquet(cache)

    wm_cols = WM_CHANNEL[house]
    raw = pd.read_csv(
        clean_csv_path(house),
        usecols=["Unix", "Aggregate", "Issues", *wm_cols],
        dtype={"Unix": "int64", "Aggregate": "float32", "Issues": "float32",
               **{c: "float32" for c in wm_cols}},
    )
    raw["wm"] = raw[wm_cols].sum(axis=1, min_count=1)
    raw = raw.drop(columns=wm_cols).rename(
        columns={"Aggregate": "aggregate", "Issues": "issues"})

    raw.index = pd.to_datetime(raw.pop("Unix"), unit="s", utc=True)
    raw = raw.sort_index()
    raw = raw[~raw.index.duplicated(keep="first")]

    grouped = raw.resample("1min")
    out = grouped[["aggregate", "wm", "issues"]].mean().astype("float32")
    out["n_samples"] = grouped["aggregate"].count().astype("int16")
    out.to_parquet(cache)
    return out


def add_local_time(df: pd.DataFrame) -> pd.DataFrame:
    local = df.index.tz_convert(LOCAL_TZ)
    df = df.copy()
    df["hour"] = local.hour
    df["dow"] = local.dayofweek
    df["date"] = local.date
    return df
