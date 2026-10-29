"""Part 1 - inspection and cleaning of raw REFIT House 1, resampled to 1 minute.

Pipeline (each step is counted in outputs/raw_h1_steps.csv)
 1. Parse      read RAW_House1_Part1.csv and _Part2.csv; Unix is the clock.
 2. Timezone   Part1 was logged in UK *local* wall-clock time stored as if it were
               UTC (evidence: an hour of timestamps repeats at the 27 Oct 2013
               clock change, the 01:00 hour is missing on 30 Mar 2014, and the
               official cleaned file is 3600 s earlier during BST only). Part1 is
               converted local -> UTC; inside the repeated hour the file order
               decides which pass is BST and which is GMT. Part2 is already UTC.
 3. Overlap    Part1 and Part2 both cover 27 Jun - 1 Oct 2014. Part1 is used up
               to its last reading and Part2 only afterwards (Part1 is denser in
               the overlap and is what the official cleaned file follows).
 4. Invalid    readings that are physically impossible become NaN:
               IAM > 4000 W (includes sensor codes 32767 / 65535 / 98301 ...),
               aggregate > 15 kW, negative values. NaN, not 0, so they are not
               mistaken for "appliance off".
 5. Duplicates sort by timestamp; exact duplicate rows are dropped; rows that
               share a timestamp but differ are merged column-wise keeping the
               last non-missing value (Part2 splits one poll over several rows).
 6. Resample   mean of readings in each UTC minute (keeps energy).
 6b. Consistency  an appliance minute above 1.1 x aggregate + 50 W is impossible
               (glitch values such as 2048 W pass the 4 kW limit) -> NaN.
 7. Gaps       holes of <= SHORT_GAP_MIN minutes are forward-filled (a sensor
               that does not report usually means "no change"); longer holes
               stay NaN and are listed as outages in outputs/raw_h1_outages.csv.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from config import (FIGURES, HOUSE1_CHANNELS, INTERIM, LOCAL_TZ, LONG_GAP_FLAG_MIN,
                    MAX_AGGREGATE_W, MAX_IAM_W, OUTPUTS, RAW_DIR, SHORT_GAP_MIN)
from clean_data import clean_csv_path

POWER_COLS = list(HOUSE1_CHANNELS)
steps = []


def log(step, **kv):
    steps.extend({"step": step, "metric": k, "value": v} for k, v in kv.items())
    print(step, kv)


def read_part(n: int) -> pd.DataFrame:
    df = pd.read_csv(RAW_DIR / f"RAW_House1_Part{n}.csv")
    df["part"] = n
    df["file_order"] = np.arange(len(df))
    return df


def inspect(df: pd.DataFrame, name: str) -> dict:
    u = df["Unix"]
    d = u.diff()
    vals = df[POWER_COLS]
    return {
        "file": name,
        "rows": len(df),
        "first": pd.to_datetime(u.min(), unit="s"),
        "last": pd.to_datetime(u.max(), unit="s"),
        "time_parse_failures": int(pd.to_datetime(df["Time"], errors="coerce").isna().sum()),
        "out_of_order_steps": int((d < 0).sum()),
        "duplicate_timestamps": int(u.duplicated().sum()),
        "exact_duplicate_rows": int(df.duplicated(subset=["Unix", *POWER_COLS]).sum()),
        "median_interval_s": float(d.median()),
        "p99_interval_s": float(d.quantile(0.99)),
        "gaps_over_5min": int((d > 300).sum()),
        "gaps_over_1h": int((d > 3600).sum()),
        "longest_gap_h": round(float(d.max()) / 3600, 1),
        "nan_cells_pct": round(100 * vals.isna().to_numpy().mean(), 2),
        "aggregate_over_15kW": int((vals["Aggregate"] > MAX_AGGREGATE_W).sum()),
        "iam_over_4kW": int((vals.drop(columns="Aggregate") > MAX_IAM_W).to_numpy().sum()),
        "negative_values": int((vals < 0).to_numpy().sum()),
        "max_iam_value": float(vals.drop(columns="Aggregate").max().max()),
        "max_aggregate": float(vals["Aggregate"].max()),
    }


def local_to_utc(df: pd.DataFrame) -> pd.Series:
    """Unix seconds that encode UK wall-clock time -> true UTC timestamps."""
    wall = pd.to_datetime(df["Unix"], unit="s")
    # Rows in a repeated (fall-back) hour: the first pass is BST, the second GMT.
    # The second pass starts where the file's timestamps jump backwards.
    back = np.flatnonzero(np.diff(df["Unix"].to_numpy()) < 0) + 1
    is_dst = np.ones(len(df), dtype=bool)
    for b in back:
        is_dst[b:] = False
        # only the repeated hour itself is ambiguous; after it, tz rules decide
    local = wall.dt.tz_localize(LOCAL_TZ, ambiguous=is_dst, nonexistent="shift_forward")
    return local.dt.tz_convert("UTC")


def to_minutes(df: pd.DataFrame) -> pd.DataFrame:
    return df.set_index("ts")[POWER_COLS].resample("1min").mean()


def fill_short_gaps(m: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Forward-fill NaN runs <= SHORT_GAP_MIN per column; list longer outages."""
    filled = m.copy()
    for col in POWER_COLS:
        s = m[col]
        run_id = s.notna().cumsum()
        run_len = s.isna().groupby(run_id).transform("sum")
        short = s.isna() & (run_len <= SHORT_GAP_MIN)
        filled.loc[short, col] = s.ffill()[short]
    # Outages: minutes where the aggregate is still missing after filling.
    miss = filled["Aggregate"].isna().astype(int).to_numpy()
    edges = np.diff(np.r_[0, miss, 0])
    starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
    out = pd.DataFrame({"start_utc": filled.index[starts],
                        "end_utc": filled.index[ends - 1],
                        "minutes": ends - starts})
    out = out[out.minutes > LONG_GAP_FLAG_MIN].reset_index(drop=True)
    return filled, out


def naive_minutes(parts) -> pd.DataFrame:
    """'Before' view: raw values as recorded, raw Unix clock, both parts stacked."""
    df = pd.concat(parts)
    df["ts"] = pd.to_datetime(df["Unix"], unit="s", utc=True)
    return to_minutes(df)


def plot_before_after(before, after, start, end, fname, title):
    start, end = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
    cols = [("Aggregate", "Aggregate"), ("Appliance5", "Washing machine"),
            ("Appliance1", "Fridge")]
    fig, axes = plt.subplots(len(cols), 2, figsize=(15, 8), sharex="col")
    for r, (col, label) in enumerate(cols):
        for c, (df, name) in enumerate([(before, "Before (raw)"), (after, "After cleaning")]):
            ax = axes[r, c]
            sl = df.loc[start:end, col]
            ax.plot(sl.index.tz_convert(LOCAL_TZ), sl.values, lw=0.6,
                    color="tab:red" if c == 0 else "tab:green")
            ax.set_title(f"{name}: {label}", fontsize=10)
            ax.set_ylabel("W")
            ax.set_xlim(start.tz_convert(LOCAL_TZ), end.tz_convert(LOCAL_TZ))
    fig.suptitle(title)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(FIGURES / fname, dpi=120)
    plt.close(fig)


def main():
    p1, p2 = read_part(1), read_part(2)
    report = pd.DataFrame([inspect(p1, "Part1"), inspect(p2, "Part2")])
    report.to_csv(OUTPUTS / "raw_h1_inspection.csv", index=False)
    print(report.T.to_string())
    before = naive_minutes([p1, p2])

    # 2. timezone
    p1["ts"] = local_to_utc(p1)
    p2["ts"] = pd.to_datetime(p2["Unix"], unit="s", utc=True)
    log("timezone", part1_rows_shifted_1h=int((p1["ts"].astype("int64") // 10**9 != p1["Unix"]).sum()))

    # 3. overlap
    p1_end = p1["ts"].max()
    dropped = int((p2["ts"] <= p1_end).sum())
    p2 = p2[p2["ts"] > p1_end]
    log("overlap", part2_rows_dropped=dropped, part1_last=str(p1_end))
    df = pd.concat([p1, p2], ignore_index=True)

    # 4. invalid values
    iam = [c for c in POWER_COLS if c != "Aggregate"]
    bad_iam = df[iam] > MAX_IAM_W
    bad_agg = df["Aggregate"] > MAX_AGGREGATE_W
    neg = df[POWER_COLS] < 0
    df[iam] = df[iam].mask(bad_iam)
    df["Aggregate"] = df["Aggregate"].mask(bad_agg)
    df[POWER_COLS] = df[POWER_COLS].mask(neg)
    log("invalid", iam_over_4kW=int(bad_iam.to_numpy().sum()),
        aggregate_over_15kW=int(bad_agg.sum()), negative=int(neg.to_numpy().sum()))

    # 5. sort + duplicates
    n0 = len(df)
    df = df.sort_values(["ts", "part", "file_order"], kind="stable")
    df = df.drop_duplicates(subset=["ts", *POWER_COLS])
    n1 = len(df)
    df = df.groupby("ts", as_index=False)[POWER_COLS].last()
    log("duplicates", exact_dupes_dropped=n0 - n1, conflicting_rows_merged=n1 - len(df),
        rows_after=len(df))

    # 6-7. resample + gaps
    minutes = to_minutes(df)
    log("resample", minutes=len(minutes),
        minutes_with_no_aggregate_pct=round(100 * minutes["Aggregate"].isna().mean(), 2))
    # 6b. consistency: an appliance cannot draw more than the whole house. This
    # catches glitch values below 4 kW (e.g. 2048 W while the house uses 190 W).
    # Tolerance: 10% + 50 W for sensors that are not synchronised.
    over = minutes[iam].gt(1.1 * minutes["Aggregate"] + 50, axis=0)
    minutes[iam] = minutes[iam].mask(over)
    log("iam_exceeds_aggregate", iam_minutes_set_nan=int(over.to_numpy().sum()),
        by_channel=over.sum().to_dict())
    cleaned, outages = fill_short_gaps(minutes)
    cleaned["outage"] = cleaned["Aggregate"].isna()
    log("gaps", short_gap_minutes_filled=int(minutes["Aggregate"].isna().sum() - cleaned["Aggregate"].isna().sum()),
        outages_over_5min=len(outages), outage_minutes=int(outages.minutes.sum()),
        longest_outage_days=round(outages.minutes.max() / 1440, 1))
    cleaned.to_parquet(INTERIM / "raw_h1_cleaned_1min.parquet")
    outages.to_csv(OUTPUTS / "raw_h1_outages.csv", index=False)

    # Sanity check against the official cleaned file (also resampled to 1 min).
    off = pd.read_csv(clean_csv_path(1), usecols=["Unix", *POWER_COLS])
    off["ts"] = pd.to_datetime(off["Unix"], unit="s", utc=True)
    official = to_minutes(off.drop_duplicates("ts"))
    both = pd.concat({"ours": cleaned["Aggregate"], "official": official["Aggregate"]}, axis=1).dropna()
    naive = pd.concat({"naive": before["Aggregate"], "official": official["Aggregate"]}, axis=1).dropna()
    log("check_vs_official",
        overlap_minutes=len(both),
        corr_ours=round(both.corr().iloc[0, 1], 4),
        mae_ours_W=round((both.ours - both.official).abs().mean(), 1),
        corr_naive_raw=round(naive.corr().iloc[0, 1], 4),
        mae_naive_raw_W=round((naive.naive - naive.official).abs().mean(), 1))
    pd.DataFrame(steps).to_csv(OUTPUTS / "raw_h1_steps.csv", index=False)

    # Plots: a summer week (shows DST shift + sentinel spikes) and the clock change.
    spike_day = before.loc["2014-04":"2014-09", "Appliance1"].idxmax()
    w0 = spike_day.tz_convert("UTC").tz_localize(None).normalize() - pd.Timedelta("2D")
    plot_before_after(before, cleaned, w0, w0 + pd.Timedelta("4D"),
                      "p1_before_after_week.png",
                      "House 1 raw vs cleaned, 1-minute (red: as recorded incl. sensor error codes; green: cleaned)")
    plot_before_after(before, cleaned, "2014-02-01", "2014-03-31",
                      "p1_before_after_outage.png",
                      "House 1 Feb-Mar 2014: long outage left as a gap (not filled)")
    # Whole-period coverage
    fig, ax = plt.subplots(figsize=(14, 3))
    daily = cleaned["Aggregate"].resample("1D").apply(lambda s: s.notna().mean() * 100)
    ax.bar(daily.index, daily.values, width=1, color="tab:green")
    ax.set(title="House 1 (raw, cleaned): % of minutes with an aggregate reading per day",
           ylabel="% coverage")
    fig.tight_layout()
    fig.savefig(FIGURES / "p1_daily_coverage.png", dpi=120)
    plt.close(fig)


if __name__ == "__main__":
    main()
