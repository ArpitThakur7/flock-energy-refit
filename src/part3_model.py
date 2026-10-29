"""Part 3 - washing-machine disaggregation from the 1-minute aggregate.

Approach (seq2point-style regression with gradient boosting)
    For every minute t the model sees a window of household aggregate power from
    t-30 to t+30 minutes, summarised as raw lags plus rolling statistics, and
    predicts the washing-machine power at t. The window idea follows
    Zhang et al. (2018) "Sequence-to-point learning with neural networks for
    NILM"; the regressor is XGBoost instead of a CNN to keep it simple and fast.

Validation: leave-one-house-out (LOHO). Each house is the test home once and
never contributes to training or early stopping in that fold. Inside the
training houses the last VAL_FRACTION of each house's timeline is used only for
early stopping. Because the test home is a different household, overlapping
windows cannot leak between train and test.

Baselines
    always_off   - predict 0 W.
    hour_of_week - mean washing-machine power for each (weekday, hour) in the
                   training houses: a "typical usage profile" that knows nothing
                   about the test house's aggregate.

Outputs: outputs/model_metrics.csv, outputs/model_daily_energy.csv, figures/p3_*.png
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xgboost as xgb

from clean_data import load_wm_house
from config import (CONTEXT_MIN, FIGURES, LOCAL_TZ, MODEL_HOUSES, OFF_SAMPLE_RATE,
                    OUTPUTS, SEED, SHORT_GAP_MIN, VAL_FRACTION, WINDOW_HALF, WM_ON_W)
from cycles import cycle_mask, detect_cycles

ROLL_WINDOWS = [5, 15, 31, 61]
TIME_FEATURES = ["hour_sin", "hour_cos", "weekend"]
# Ablation switch: REFIT_NO_TIME=1 trains on aggregate-shape features only.
USE_TIME_FEATURES = os.environ.get("REFIT_NO_TIME") != "1"
SUFFIX = "" if USE_TIME_FEATURES else "_notime"


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate-only features for each minute (centred window -> uses future too)."""
    agg = df["aggregate"].ffill(limit=SHORT_GAP_MIN)   # fill only very short holes
    feats = {}
    for k in range(-WINDOW_HALF, WINDOW_HALF + 1, 2):
        feats[f"lag_{k}"] = agg.shift(-k)
    # Baseline-removed level: how far above the local minimum the house is, which
    # transfers better across homes with different always-on load.
    base = agg.rolling(121, center=True, min_periods=60).min()
    feats["above_base"] = agg - base
    for w in ROLL_WINDOWS:
        r = agg.rolling(w, center=True, min_periods=w // 2 + 1)
        feats[f"mean_{w}"] = r.mean() - base
        feats[f"std_{w}"] = r.std()
        feats[f"max_{w}"] = r.max() - base
        feats[f"min_{w}"] = r.min() - base
        # time spent above 1.5 kW in the window - long heating plateaus are typical
        feats[f"hi_{w}"] = (agg > 1500).astype("float32").rolling(w, center=True, min_periods=1).mean()
    d = agg.diff()
    feats["diff"] = d
    feats["absdiff_sum_15"] = d.abs().rolling(15, center=True, min_periods=8).sum()
    local = df.index.tz_convert(LOCAL_TZ)
    feats["hour_sin"] = np.sin(2 * np.pi * local.hour / 24)
    feats["hour_cos"] = np.cos(2 * np.pi * local.hour / 24)
    feats["weekend"] = (local.dayofweek >= 5).astype("float32")
    return pd.DataFrame(feats, index=df.index).astype("float32")


def prepare_house(house: int) -> pd.DataFrame:
    df = load_wm_house(house)
    X = build_features(df)
    out = X.assign(
        target=df["wm"].clip(0, 4000),
        aggregate=df["aggregate"],
        house=house,
        # usable = full feature window, real target, and a target that is physically
        # possible (WM not above the whole house). REFIT's own Issues flag is NOT
        # used: it fires on 17-47% of WM-on minutes (sum of 9 unsynchronised IAMs vs
        # aggregate), so dropping it would remove washes and bias the evaluation.
        usable=(X.notna().all(axis=1) & df["wm"].notna()
                & (df["wm"] <= 1.1 * df["aggregate"] + 50)),
    )
    cycles = detect_cycles(df["wm"])
    near = cycle_mask(df.index, cycles.assign(
        start=cycles.start - pd.Timedelta(minutes=CONTEXT_MIN),
        end=cycles.end + pd.Timedelta(minutes=CONTEXT_MIN)))
    out["near_cycle"] = near
    return out[out["usable"]]


def subsample(df: pd.DataFrame, rng) -> tuple[pd.DataFrame, np.ndarray]:
    """Keep every minute near a cycle, OFF_SAMPLE_RATE of the rest, re-weighted
    by 1/rate so the training loss still reflects the true on/off balance."""
    keep_off = rng.random(len(df)) < OFF_SAMPLE_RATE
    mask = df["near_cycle"].to_numpy() | keep_off
    w = np.where(df["near_cycle"].to_numpy(), 1.0, 1.0 / OFF_SAMPLE_RATE)[mask]
    return df[mask], w


THRESHOLD_GRID = [20, 50, 100, 150, 200, 300, 400, 600]


def postprocess(pred: np.ndarray, aggregate: np.ndarray, threshold: float = WM_ON_W) -> np.ndarray:
    """Physical constraints: 0 <= WM <= aggregate; predictions below `threshold` -> 0."""
    pred = np.clip(pred, 0, np.maximum(aggregate, 0))
    pred[pred < threshold] = 0
    return pred


def cycle_filter(pred: np.ndarray, index: pd.DatetimeIndex) -> np.ndarray:
    """Keep predicted power only inside predicted blocks that pass the Part 2 cycle
    rule (>= 10 min, >= 0.05 kWh, peak >= 200 W). Removes short false alarms such
    as a kettle or a few minutes of an oven element."""
    full = pd.date_range(index[0], index[-1], freq="1min")
    s = pd.Series(pred, index=index).reindex(full)
    keep = cycle_mask(full, detect_cycles(s))
    return np.where(pd.Series(keep, index=full).reindex(index).to_numpy(), pred, 0.0)


def minute_f1(y, p):
    on_t, on_p = y > WM_ON_W, p > WM_ON_W
    tp = (on_t & on_p).sum()
    return 2 * tp / max(on_t.sum() + on_p.sum(), 1)


def choose_threshold(booster, val, feature_cols):
    """Zeroing threshold that maximises minute F1 on the training houses' held-out
    time tail. The test house is never used, so this is not tuned on test data."""
    raw = booster.predict(xgb.DMatrix(val[feature_cols]),
                          iteration_range=(0, booster.best_iteration + 1))
    y, agg = val["target"].to_numpy(), val["aggregate"].to_numpy()
    scores = {t: minute_f1(y, postprocess(raw, agg, t)) for t in THRESHOLD_GRID}
    return max(scores, key=scores.get)


def event_scores(y: np.ndarray, p: np.ndarray, index: pd.DatetimeIndex) -> dict:
    """Cycle-level detection. Cycles are found with the same rule as Part 2 on the
    actual and on the predicted series; a cycle counts as matched if it overlaps
    any cycle in the other series."""
    full = pd.date_range(index[0], index[-1], freq="1min")
    ty = detect_cycles(pd.Series(y, index=index).reindex(full))
    tp_ = detect_cycles(pd.Series(p, index=index).reindex(full))

    def overlap_share(a, b):
        if len(a) == 0:
            return np.nan
        if len(b) == 0:
            return 0.0
        bs, be = b.start.to_numpy(), b.end.to_numpy()
        hits = [((bs <= e) & (be >= s)).any() for s, e in zip(a.start.to_numpy(), a.end.to_numpy())]
        return float(np.mean(hits))

    rec, prec = overlap_share(ty, tp_), overlap_share(tp_, ty)
    return {"true_cycles": len(ty), "pred_cycles": len(tp_),
            "cycle_recall": rec, "cycle_precision": prec,
            "cycle_F1": 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0}


def metrics(y: np.ndarray, p: np.ndarray, index: pd.DatetimeIndex) -> dict:
    on_t, on_p = y > WM_ON_W, p > WM_ON_W
    tp = (on_t & on_p).sum()
    prec = tp / max(on_p.sum(), 1)
    rec = tp / max(on_t.sum(), 1)
    daily = pd.DataFrame({"y": y, "p": p}, index=index.tz_convert(LOCAL_TZ)).resample("1D").sum() / 60 / 1000
    daily = daily[daily.y.notna()]
    return {
        "MAE_W": np.abs(y - p).mean(),
        "MAE_on_W": np.abs(y - p)[on_t].mean(),
        "energy_true_kWh": y.sum() / 60 / 1000,
        "energy_pred_kWh": p.sum() / 60 / 1000,
        "energy_err_pct": 100 * (p.sum() - y.sum()) / y.sum(),
        "daily_kWh_MAE": (daily.p - daily.y).abs().mean(),
        "precision": prec, "recall": rec,
        "F1": 2 * prec * rec / max(prec + rec, 1e-9),
        **event_scores(y, p, index),
    }


def hour_of_week_profile(train: pd.DataFrame) -> pd.Series:
    local = train.index.tz_convert(LOCAL_TZ)
    return train["target"].groupby([local.dayofweek, local.hour]).mean()


def apply_profile(profile: pd.Series, index: pd.DatetimeIndex) -> np.ndarray:
    local = index.tz_convert(LOCAL_TZ)
    keys = pd.MultiIndex.from_arrays([local.dayofweek, local.hour])
    return profile.reindex(keys).fillna(0).to_numpy()


def train_fold(train_parts, feature_cols, rng):
    tr, va, va_full, w_tr, w_va = [], [], [], [], []
    for part in train_parts:
        cut = part.index[int(len(part) * (1 - VAL_FRACTION))]
        a, wa = subsample(part[part.index < cut], rng)
        b, wb = subsample(part[part.index >= cut], rng)
        tr.append(a); va.append(b); w_tr.append(wa); w_va.append(wb)
        va_full.append(part[part.index >= cut])
    tr, va = pd.concat(tr), pd.concat(va)
    dtr = xgb.DMatrix(tr[feature_cols], label=tr["target"], weight=np.concatenate(w_tr))
    dva = xgb.DMatrix(va[feature_cols], label=va["target"], weight=np.concatenate(w_va))
    params = {
        "objective": "reg:squarederror", "eta": 0.05, "max_depth": 8,
        "subsample": 0.8, "colsample_bytree": 0.8, "min_child_weight": 20,
        "tree_method": "hist", "device": "cuda", "seed": SEED, "eval_metric": "mae",
    }
    try:
        booster = xgb.train(params, dtr, 2000, evals=[(dva, "val")],
                            early_stopping_rounds=50, verbose_eval=False)
    except xgb.core.XGBoostError:          # no GPU -> CPU
        params["device"] = "cpu"
        booster = xgb.train(params, dtr, 2000, evals=[(dva, "val")],
                            early_stopping_rounds=50, verbose_eval=False)
    return booster, len(tr), pd.concat(va_full)


def plot_actual_vs_pred(test, house, path, title_extra=""):
    """Pick the test day with the most true WM energy among full-coverage days and
    plot aggregate, actual and predicted WM."""
    local = test.tz_convert(LOCAL_TZ)
    day_energy = local["target"].groupby(local.index.date).sum()
    day_count = local["target"].groupby(local.index.date).size()
    candidates = day_energy[day_count >= 1400]
    # a typical washing day: median energy among days with at least one cycle
    washing_days = candidates[candidates > 0.3 * candidates.max()]
    day = washing_days.sort_values().index[len(washing_days) // 2]
    sl = local.loc[str(day)]
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(sl.index, sl["aggregate"], color="0.75", lw=0.7, label="Aggregate (input)")
    ax.plot(sl.index, sl["target"], color="tab:blue", lw=1.2, label="Actual washing machine")
    ax.plot(sl.index, sl["pred"], color="tab:orange", lw=1.2, ls="--", label="Predicted washing machine")
    ax.set(title=f"House {house} (unseen test home) - {day} {title_extra}", ylabel="Power (W)")
    ax.legend(loc="upper left")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return day


def main():
    rng = np.random.default_rng(SEED)
    data = {h: prepare_house(h) for h in MODEL_HOUSES}
    feature_cols = [c for c in data[MODEL_HOUSES[0]].columns
                    if c not in ("target", "aggregate", "house", "usable", "near_cycle")]
    if not USE_TIME_FEATURES:
        feature_cols = [c for c in feature_cols if c not in TIME_FEATURES]
    print(f"{len(feature_cols)} features (time features: {USE_TIME_FEATURES})")
    rows, daily_rows, preds = [], [], {}
    importances = []
    for test_house in MODEL_HOUSES:
        train_parts = [data[h] for h in MODEL_HOUSES if h != test_house]
        booster, n_train, val_full = train_fold(train_parts, feature_cols, rng)
        threshold = choose_threshold(booster, val_full, feature_cols)
        test = data[test_house].copy()
        raw = booster.predict(xgb.DMatrix(test[feature_cols]),
                              iteration_range=(0, booster.best_iteration + 1))
        agg = test["aggregate"].to_numpy()
        unfiltered = postprocess(raw, agg, threshold)
        test["pred"] = cycle_filter(unfiltered, test.index)     # final model output
        profile = hour_of_week_profile(pd.concat(train_parts))
        candidates = {
            "always_off": np.zeros(len(test)),
            "hour_of_week": apply_profile(profile, test.index),
            "xgboost_window": unfiltered,
            "xgboost_window+cycle_filter": test["pred"].to_numpy(),
        }
        y = test["target"].to_numpy()
        for name, p in candidates.items():
            m = metrics(y, p, test.index)
            rows.append({"test_house": test_house, "model": name,
                         "threshold_W": threshold if name.startswith("xgboost") else np.nan, **m})
        local = test.tz_convert(LOCAL_TZ)
        daily = local[["target", "pred"]].resample("1D").sum() / 60 / 1000
        daily = daily[local["target"].resample("1D").count() >= 1400]
        daily_rows.append(daily.assign(house=test_house))
        preds[test_house] = test[["aggregate", "target", "pred"]]
        gain = booster.get_score(importance_type="gain")
        importances.append(pd.Series(gain, name=test_house))
        print(f"test house {test_house}: trained on {n_train:,} rows, "
              f"best iteration {booster.best_iteration}, threshold {threshold} W")

    res = pd.DataFrame(rows)
    res.to_csv(OUTPUTS / f"model_metrics{SUFFIX}.csv", index=False)
    summary = res.groupby("model")[["MAE_W", "MAE_on_W", "energy_err_pct", "daily_kWh_MAE",
                                    "precision", "recall", "F1", "cycle_recall",
                                    "cycle_precision", "cycle_F1"]].mean()
    summary["abs_energy_err_pct"] = res.assign(a=res.energy_err_pct.abs()).groupby("model").a.mean()
    summary.to_csv(OUTPUTS / f"model_metrics_mean{SUFFIX}.csv")
    daily_all = pd.concat(daily_rows)
    daily_all.to_csv(OUTPUTS / f"model_daily_energy{SUFFIX}.csv")
    imp = pd.concat(importances, axis=1).mean(axis=1).sort_values(ascending=False)
    imp.to_csv(OUTPUTS / f"model_feature_importance{SUFFIX}.csv", header=["mean_gain"])

    if not USE_TIME_FEATURES:       # ablation run: metrics only
        print(summary.round(3).to_string())
        return
    # Actual vs predicted traces for every test house
    for h, test in preds.items():
        plot_actual_vs_pred(test, h, FIGURES / f"p3_actual_vs_pred_h{h}{SUFFIX}.png")

    # Daily energy scatter (all LOHO folds)
    ncols = min(6, len(preds))
    nrows = int(np.ceil(len(preds) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(3.2 * ncols, 3.2 * nrows), sharex=True, sharey=True)
    axes = np.atleast_1d(axes).ravel()
    lim = daily_all[["target", "pred"]].quantile(0.995).max()
    for ax, (h, d) in zip(axes, daily_all.groupby("house")):
        r = d[["target", "pred"]].corr().iloc[0, 1]
        ax.scatter(d.target, d.pred, s=5, alpha=0.4)
        ax.plot([0, lim], [0, lim], "k--", lw=0.8)
        ax.set(title=f"House {h} (r={r:.2f})", xlim=(0, lim), ylim=(0, lim))
    for ax in axes[len(preds):]:
        ax.set_visible(False)
    for ax in axes[::ncols]:
        ax.set_ylabel("Predicted kWh/day")
    for ax in axes[-ncols:]:
        ax.set_xlabel("Actual kWh/day")
    fig.suptitle("Daily washing-machine energy: actual vs predicted (leave-one-house-out)")
    fig.tight_layout()
    fig.savefig(FIGURES / f"p3_daily_energy_scatter{SUFFIX}.png", dpi=130)
    plt.close(fig)

    pd.set_option("display.width", 200)
    print(res.round(3).to_string(index=False))
    print(summary.round(3).to_string())
    print(imp.head(10).round(0).to_string())


if __name__ == "__main__":
    main()
