"""Part 2 - exploratory analysis of washing-machine use (official cleaned REFIT data).

Outputs
    outputs/wm_quality.csv       availability / data quality per house
    outputs/wm_cycles.csv        every detected cycle
    outputs/wm_cycle_summary.csv cycle characteristics per house
    figures/p2_*.png             plots referenced in RESULTS.md
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from clean_data import add_local_time, load_wm_house
from config import EDA_HOUSES, FIGURES, LOCAL_TZ, OUTPUTS, WM_ON_W
from cycles import detect_cycles

DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def quality_row(house: int, df: pd.DataFrame, cycles: pd.DataFrame) -> dict:
    present = df["n_samples"] > 0
    # Contiguous runs of missing minutes -> outage lengths.
    miss = (~present).astype(int).to_numpy()
    edges = np.diff(np.r_[0, miss, 0])
    gap_lengths = np.flatnonzero(edges == -1) - np.flatnonzero(edges == 1)
    avail = df[present]
    days = (df.index[-1] - df.index[0]).total_seconds() / 86400
    return {
        "house": house,
        "start": df.index[0].tz_convert(LOCAL_TZ).date(),
        "end": df.index[-1].tz_convert(LOCAL_TZ).date(),
        "span_days": round(days, 1),
        "minutes_total": len(df),
        "missing_min_pct": round(100 * (~present).mean(), 2),
        "gaps_over_1h": int((gap_lengths > 60).sum()),
        "longest_gap_days": round(gap_lengths.max() / 1440, 1) if len(gap_lengths) else 0,
        "issues_flag_pct": round(100 * (avail["issues"] > 0).mean(), 2),
        "wm_exactly_zero_pct": round(100 * (avail["wm"] == 0).mean(), 2),
        "wm_off_pct": round(100 * (avail["wm"] <= WM_ON_W).mean(), 2),
        "n_cycles": len(cycles),
        "cycles_per_week": round(len(cycles) / (present.sum() / 1440 / 7), 2),
        "wm_kwh_per_day": round(avail["wm"].sum() / 60 / 1000 / (present.sum() / 1440), 3),
        "agg_kwh_per_day": round(avail["aggregate"].sum() / 60 / 1000 / (present.sum() / 1440), 2),
    }


def plot_representative_day(house, df, cycles):
    """(i) 24 h aggregate + WM trace on a day with a typical cycle."""
    # Typical wash = cycle energy closest to the house median, on a day with
    # (almost) complete data so the 24 h trace is not cut by an outage.
    local = df.tz_convert(LOCAL_TZ)
    coverage = (local["n_samples"] > 0).groupby(local.index.date).mean()
    order = (cycles.energy_kwh - cycles.energy_kwh.median()).abs().sort_values().index
    for i in order:
        day = cycles.loc[i, "start"].tz_convert(LOCAL_TZ).normalize()
        if coverage.get(day.date(), 0) >= 0.99:
            break
    sl = local.loc[day: day + pd.Timedelta("1D")]
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(sl.index, sl["aggregate"], lw=0.7, color="0.4", label="Aggregate")
    ax.fill_between(sl.index, 0, sl["wm"], color="tab:blue", alpha=0.6, label="Washing machine")
    ax.set_title(f"House {house} - {day.date()} ({day.day_name()}): aggregate vs washing machine (1-min)")
    ax.set_ylabel("Power (W)")
    ax.legend(loc="upper left")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(FIGURES / "p2_representative_day.png", dpi=130)
    plt.close(fig)
    return day.date()


def plot_cycles(all_cycles, data):
    """(ii) Detected cycles: three examples per house, aligned at cycle start."""
    ncols = min(4, len(data))
    nrows = int(np.ceil(len(data) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.2 * ncols, 3.2 * nrows), sharey=True)
    axes = np.atleast_1d(axes).ravel()
    for ax in axes[len(data):]:
        ax.set_visible(False)
    for ax, (house, df) in zip(axes, data.items()):
        cyc = all_cycles[all_cycles.house == house]
        picks = cyc.iloc[np.linspace(0, len(cyc) - 1, 3).astype(int)]
        for _, c in picks.iterrows():
            seg = df.wm.loc[c.start - pd.Timedelta("10min"): c.end + pd.Timedelta("10min")]
            minutes = (seg.index - c.start).total_seconds() / 60
            ax.plot(minutes, seg.values, lw=1,
                    label=f"{c.start.tz_convert(LOCAL_TZ):%Y-%m-%d} "
                          f"{c.duration_min:.0f} min, {c.energy_kwh:.2f} kWh")
        ax.axhline(WM_ON_W, color="red", ls=":", lw=0.8)
        ax.set_title(f"House {house}")
        ax.set_xlabel("Minutes from cycle start")
        ax.legend(fontsize=6)
    for ax in axes[::ncols]:
        ax.set_ylabel("WM power (W)")
    fig.suptitle("Detected washing-machine cycles (red dotted line = 20 W on-threshold)")
    fig.tight_layout()
    fig.savefig(FIGURES / "p2_detected_cycles.png", dpi=130)
    plt.close(fig)


def plot_cross_house(all_cycles):
    """(iii) Cross-house comparison of cycle duration, energy and peak power."""
    houses = sorted(all_cycles.house.unique())
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    for ax, col, label in zip(axes, ["duration_min", "energy_kwh", "peak_w"],
                              ["Duration (min)", "Energy per cycle (kWh)", "Peak power (W)"]):
        ax.boxplot([all_cycles.loc[all_cycles.house == h, col] for h in houses],
                   tick_labels=[f"H{h}" for h in houses], showfliers=False)
        ax.set_title(label)
    fig.suptitle("Washing-machine cycle characteristics by house (outliers hidden)")
    fig.tight_layout()
    fig.savefig(FIGURES / "p2_cross_house.png", dpi=130)
    plt.close(fig)


def plot_usage_patterns(all_cycles, avail_days):
    """Hour-of-day and day-of-week of cycle starts, normalised per house (heatmaps)."""
    hour_rows, dow_rows = {}, {}
    for house, cyc in all_cycles.groupby("house"):
        start = cyc.start.dt.tz_convert(LOCAL_TZ)
        by_hour = start.dt.hour.value_counts().reindex(range(24), fill_value=0)
        hour_rows[f"H{house}"] = 100 * by_hour / by_hour.sum()
        by_dow = start.dt.dayofweek.value_counts().reindex(range(7), fill_value=0)
        # cycles per available week, so houses with more outages are comparable
        dow_rows[f"H{house}"] = by_dow / (avail_days[house] / 7)
    hours, dows = pd.DataFrame(hour_rows).T, pd.DataFrame(dow_rows).T
    all_starts = all_cycles.start.dt.tz_convert(LOCAL_TZ)
    fig, axes = plt.subplots(1, 3, figsize=(18, 4.5), gridspec_kw={"width_ratios": [3, 1.3, 1.6]})
    im = axes[0].imshow(hours, aspect="auto", cmap="Blues")
    axes[0].set(title="Cycle start hour (local) - % of each house's cycles", xlabel="Hour of day",
                yticks=range(len(hours)), yticklabels=hours.index, xticks=range(0, 24, 2))
    fig.colorbar(im, ax=axes[0], fraction=0.03)
    im = axes[1].imshow(dows, aspect="auto", cmap="Oranges")
    axes[1].set(title="Cycles per available week", xticks=range(7), xticklabels=DOW,
                yticks=range(len(dows)), yticklabels=dows.index)
    fig.colorbar(im, ax=axes[1], fraction=0.05)
    pooled = pd.crosstab(all_starts.dt.dayofweek, all_starts.dt.hour).reindex(
        index=range(7), columns=range(24), fill_value=0)
    im = axes[2].imshow(100 * pooled / pooled.to_numpy().sum(), aspect="auto", cmap="Purples")
    axes[2].set(title="All houses pooled: % of cycles by weekday x hour", xlabel="Hour of day",
                yticks=range(7), yticklabels=DOW, xticks=range(0, 24, 3))
    fig.colorbar(im, ax=axes[2], fraction=0.04)
    fig.tight_layout()
    fig.savefig(FIGURES / "p2_usage_patterns.png", dpi=130)
    plt.close(fig)


def main():
    data, cycles_list, quality = {}, [], []
    for house in EDA_HOUSES:
        df = load_wm_house(house)
        # Minutes flagged by REFIT's Issues column (sub-meters > aggregate) are
        # kept for the WM channel itself but noted in the quality table.
        cyc = detect_cycles(df["wm"])
        cyc.insert(0, "house", house)
        data[house] = df
        cycles_list.append(cyc)
        quality.append(quality_row(house, df, cyc))
        print(f"House {house}: {len(cyc)} cycles")

    all_cycles = pd.concat(cycles_list, ignore_index=True)
    q = pd.DataFrame(quality)
    q.to_csv(OUTPUTS / "wm_quality.csv", index=False)
    all_cycles.to_csv(OUTPUTS / "wm_cycles.csv", index=False)

    summary = all_cycles.groupby("house").agg(
        n_cycles=("energy_kwh", "size"),
        duration_median_min=("duration_min", "median"),
        duration_iqr_min=("duration_min", lambda s: s.quantile(.75) - s.quantile(.25)),
        energy_median_kwh=("energy_kwh", "median"),
        energy_mean_kwh=("energy_kwh", "mean"),
        peak_median_w=("peak_w", "median"),
    ).round(3)
    starts = all_cycles.assign(local=all_cycles.start.dt.tz_convert(LOCAL_TZ))
    summary["weekend_share_pct"] = starts.groupby("house").local.apply(
        lambda s: round(100 * (s.dt.dayofweek >= 5).mean(), 1))
    summary["peak_start_hour"] = starts.groupby("house").local.apply(
        lambda s: s.dt.hour.mode().iloc[0])
    summary.to_csv(OUTPUTS / "wm_cycle_summary.csv")

    avail_days = {h: (d.n_samples > 0).sum() / 1440 for h, d in data.items()}
    rep_house = EDA_HOUSES[1] if len(EDA_HOUSES) > 1 else EDA_HOUSES[0]
    rep_day = plot_representative_day(rep_house, data[rep_house],
                                      all_cycles[all_cycles.house == rep_house])
    plot_cycles(all_cycles, data)
    plot_cross_house(all_cycles)
    plot_usage_patterns(all_cycles, avail_days)

    pd.set_option("display.width", 200)
    print(q.to_string(index=False))
    print(summary.to_string())
    print("Representative day:", rep_house, rep_day)


if __name__ == "__main__":
    main()
