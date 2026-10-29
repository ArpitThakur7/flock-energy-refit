"""Washing-machine cycle detection on a 1-minute power series.

Rule in plain language: the machine counts as "running" in any minute where its
average power is above WM_ON_W (20 W, comfortably above standby of a few watts).
A wash has quiet phases (soaking, draining, pauses between tumbles), so running
minutes separated by a pause of WM_BRIDGE_MIN minutes or less are joined into one
cycle. A joined block only counts as a cycle if it lasts at least
WM_MIN_DURATION_MIN minutes, uses at least WM_MIN_ENERGY_KWH and reaches at least
WM_MIN_PEAK_W at some point; this throws away blips such as the door lock or
display waking up.
"""
import numpy as np
import pandas as pd

from config import (WM_BRIDGE_MIN, WM_MIN_DURATION_MIN, WM_MIN_ENERGY_KWH,
                    WM_MIN_PEAK_W, WM_ON_W)


def detect_cycles(power: pd.Series,
                  on_w: float = WM_ON_W,
                  bridge_min: int = WM_BRIDGE_MIN,
                  min_duration_min: int = WM_MIN_DURATION_MIN,
                  min_energy_kwh: float = WM_MIN_ENERGY_KWH,
                  min_peak_w: float = WM_MIN_PEAK_W) -> pd.DataFrame:
    """Return one row per cycle: start, end, duration_min, peak_w, energy_kwh.

    `power` must be on a regular 1-minute index; NaN (missing) counts as off.
    """
    on = (power.fillna(0).to_numpy() > on_w)
    idx = np.flatnonzero(on)
    cols = ["start", "end", "duration_min", "peak_w", "energy_kwh"]
    if idx.size == 0:
        return pd.DataFrame(columns=cols)

    # Split the running minutes into blocks wherever the pause is longer than bridge_min.
    breaks = np.flatnonzero(np.diff(idx) > bridge_min + 1)
    starts = np.r_[idx[0], idx[breaks + 1]]
    ends = np.r_[idx[breaks], idx[-1]]

    values = power.fillna(0).to_numpy()
    times = power.index
    rows = []
    for s, e in zip(starts, ends):
        seg = values[s:e + 1]
        rows.append((times[s], times[e], e - s + 1, float(seg.max()),
                     float(seg.sum()) / 60 / 1000))
    cyc = pd.DataFrame(rows, columns=cols)
    keep = ((cyc.duration_min >= min_duration_min)
            & (cyc.energy_kwh >= min_energy_kwh)
            & (cyc.peak_w >= min_peak_w))
    return cyc[keep].reset_index(drop=True)


def cycle_mask(index: pd.DatetimeIndex, cycles: pd.DataFrame) -> np.ndarray:
    """Boolean array over `index`: True inside any detected cycle."""
    mask = np.zeros(len(index), dtype=bool)
    pos_start = index.searchsorted(cycles["start"])
    pos_end = index.searchsorted(cycles["end"], side="right")
    for s, e in zip(pos_start, pos_end):
        mask[s:e] = True
    return mask
