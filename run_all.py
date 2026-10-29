"""Run the whole pipeline end to end: data -> Part 1 -> Part 2 -> Part 3 (+ ablation).

    python run_all.py
"""
import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
STEPS = [
    ("get_data.py", {}),
    ("part1_clean_raw.py", {}),
    ("part2_wm_eda.py", {}),
    ("part3_model.py", {}),
    ("part3_model.py", {"REFIT_NO_TIME": "1"}),   # ablation without time features
]

for script, env in STEPS:
    print(f"\n=== {script} {env or ''}", flush=True)
    subprocess.run([sys.executable, script], cwd=SRC, check=True,
                   env={**os.environ, **env})
print("\nDone. Tables in outputs/, figures in figures/.")
