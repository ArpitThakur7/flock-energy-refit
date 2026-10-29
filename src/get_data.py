"""Download the REFIT archives (if missing) and extract only the files we use.

    python src/get_data.py

* If data/clean/CLEAN_House<N>.csv already exist (e.g. copied in by hand) they
  are left alone.
* Extraction uses the 7-Zip command line (`7z`, or C:/Program Files/7-Zip/7z.exe)
  and falls back to the `py7zr` package if 7-Zip is not installed.
"""
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from config import ARCHIVES, CLEAN_DIR, EDA_HOUSES, RAW_DIR, RAW_HOUSE, URLS

RAW_FILES = [f"RAW_House{RAW_HOUSE}_Part1.csv", f"RAW_House{RAW_HOUSE}_Part2.csv"]
CLEAN_FILES = [f"CLEAN_House{h}.csv" for h in EDA_HOUSES]


def download(name: str):
    dest = ARCHIVES / name
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    ARCHIVES.mkdir(parents=True, exist_ok=True)
    print(f"downloading {name} ...")
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(URLS[name], headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, length=1 << 20)
    tmp.rename(dest)
    return dest


def seven_zip():
    for cand in ("7z", "7za", r"C:\Program Files\7-Zip\7z.exe"):
        path = shutil.which(cand) or (cand if Path(cand).exists() else None)
        if path:
            return path
    return None


def extract(archive: Path, members: list[str], out_dir: Path):
    missing = [m for m in members if not (out_dir / m).exists()]
    if not missing:
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    exe = seven_zip()
    print(f"extracting {len(missing)} file(s) from {archive.name} ...")
    if exe:
        subprocess.run([exe, "e", "-y", f"-o{out_dir}", str(archive), *missing],
                       check=True, stdout=subprocess.DEVNULL)
    else:
        import py7zr  # pip install py7zr
        with py7zr.SevenZipFile(archive) as z:
            z.extract(path=out_dir, targets=missing)


def main():
    download("CLEAN_READ_ME_081116.txt")
    if any(not (RAW_DIR / f).exists() for f in RAW_FILES):
        extract(download("REFIT_RAW_081116.7z"), RAW_FILES, RAW_DIR)
    if any(not (CLEAN_DIR / f).exists() for f in CLEAN_FILES):
        extract(download("CLEAN_REFIT_081116.7z"), CLEAN_FILES, CLEAN_DIR)
    print("data ready:", sorted(p.name for p in RAW_DIR.glob("*.csv")),
          sorted(p.name for p in CLEAN_DIR.glob("*.csv")))


if __name__ == "__main__":
    sys.exit(main())
