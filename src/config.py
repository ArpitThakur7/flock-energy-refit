"""Shared paths, house selections and analysis constants.

Every threshold used in the analysis lives here so that the numbers quoted in
DATA.md / RESULTS.md can be traced back to one place.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ARCHIVES = DATA / "archives"          # downloaded .7z files + readme
RAW_DIR = DATA / "raw"                # extracted raw REFIT csvs
CLEAN_DIR = DATA / "clean"            # extracted cleaned REFIT csvs
INTERIM = DATA / "interim"            # 1-minute parquet caches
FIGURES = ROOT / "figures"
OUTPUTS = ROOT / "outputs"            # tables / metrics written by the pipeline

for _d in (INTERIM, FIGURES, OUTPUTS):
    _d.mkdir(parents=True, exist_ok=True)

LOCAL_TZ = "Europe/London"

# --------------------------------------------------------------------------
# Download locations. The pureportal.strath.ac.uk/files/... links quoted in the
# brief return HTTP 403 to scripted clients; the same files are served from the
# pure.strath.ac.uk/ws/portalfiles/portal/... path.
# --------------------------------------------------------------------------
URLS = {
    "REFIT_RAW_081116.7z":
        "https://pure.strath.ac.uk/ws/portalfiles/portal/62090177/REFIT_RAW_081116.7z",
    "CLEAN_REFIT_081116.7z":
        "https://pure.strath.ac.uk/ws/portalfiles/portal/62090184/CLEAN_REFIT_081116.7z",
    "CLEAN_READ_ME_081116.txt":
        "https://pure.strath.ac.uk/ws/portalfiles/portal/62090183/CLEAN_READ_ME_081116.txt",
}

# --------------------------------------------------------------------------
# Part 1 - raw House 1
# --------------------------------------------------------------------------
RAW_HOUSE = 1
# House 1 channel names from the REFIT readme (Appliance1..9).
HOUSE1_CHANNELS = {
    "Aggregate": "Aggregate",
    "Appliance1": "Fridge",
    "Appliance2": "Freezer(1)",
    "Appliance3": "Freezer(2)",
    "Appliance4": "Washer Dryer",
    "Appliance5": "Washing Machine",
    "Appliance6": "Dishwasher",
    "Appliance7": "Computer",
    "Appliance8": "Television Site",
    "Appliance9": "Electric Heater",
}
# Physical plausibility limits for active power (W). A UK domestic supply is
# typically fused at 60-100 A @ 230 V (~14-23 kW); a single 13 A plug is ~3 kW.
MAX_AGGREGATE_W = 15_000
MAX_IAM_W = 4_000          # same limit the official REFIT cleaning uses for IAMs
# Gaps (no reading at all) at 1-minute resolution.
SHORT_GAP_MIN = 5          # gaps <= this many minutes are filled (forward fill)
LONG_GAP_FLAG_MIN = 5      # anything longer is left as NaN and flagged as outage

# --------------------------------------------------------------------------
# Parts 2/3 - washing machine channel(s) in the cleaned data (from the readme).
# House 4 has two washing machines; the target there is their summed load, since
# both leave the same kind of footprint in the aggregate. House 1 also has a
# washer-dryer (Appliance4) that is *not* part of the target - a known confounder.
# --------------------------------------------------------------------------
WM_CHANNEL = {
    1: ["Appliance5"],
    2: ["Appliance2"],
    3: ["Appliance6"],
    4: ["Appliance4", "Appliance5"],
    5: ["Appliance3"],
    7: ["Appliance5"],
    15: ["Appliance3"],
    16: ["Appliance5"],
    17: ["Appliance4"],
    18: ["Appliance5"],
    19: ["Appliance2"],
    21: ["Appliance3"],
}
EDA_HOUSES = [1, 2, 3, 4, 5, 7, 15, 16, 17, 18, 19, 21]
MODEL_HOUSES = EDA_HOUSES   # leave-one-house-out over these

# Cycle detection rule (1-minute mean power of the washing-machine IAM).
WM_ON_W = 20            # above standby (0-5 W) and below any real wash phase
WM_BRIDGE_MIN = 15      # pauses (soak / drain / tumble rest) up to this are bridged
WM_MIN_DURATION_MIN = 10
WM_MIN_ENERGY_KWH = 0.05
WM_MIN_PEAK_W = 200

# Model: leave-one-house-out. For each fold the last VAL_FRACTION (by time) of
# every training house is held back for early stopping, so no tuning ever sees
# the test house.
VAL_FRACTION = 0.2
WINDOW_HALF = 30          # minutes of aggregate context either side of the target
OFF_SAMPLE_RATE = 0.1     # share of far-from-cycle minutes kept for training
CONTEXT_MIN = 60          # minutes around a cycle that are always kept

SEED = 42
