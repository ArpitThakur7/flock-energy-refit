"""Build the submission PDF: a cover, an at-a-glance page, then README, DATA,
RESULTS and Recommendation, with all figures embedded.

    python tools/build_report_pdf.py --repo-url URL [--author NAME]

Headline numbers are read from outputs/, so they always match the last run of
the pipeline. Figures are re-encoded as compressed JPEGs to keep the file under
the 1 MB upload limit. Rendering uses headless Microsoft Edge or Chrome.
"""
import argparse
import base64
import io
import re
import shutil
import subprocess
from pathlib import Path

import markdown
import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
DOCS = [("Recommendation.md", "Summary and recommendation"),
        ("README.md", "Overview, setup and design"),
        ("DATA.md", "Data quality and cleaning"),
        ("RESULTS.md", "Analysis, model and results")]
BROWSERS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "msedge", "google-chrome", "chromium", "chrome"]

CSS = """
:root { --navy:#0f2a44; --teal:#0e9f8e; --amber:#e8962e; --ink:#1f2933; --muted:#5f6b7a;
        --line:#d9e0e8; --soft:#f3f6f9; }
@page { size: A4; margin: 15mm 14mm 16mm; }
* { box-sizing: border-box; }
body { font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif; font-size: 9.4pt;
       line-height: 1.45; color: var(--ink); margin: 0; }
p { margin: 0 0 6px; }
h1 { font-size: 19pt; color: var(--navy); margin: 0 0 10px; line-height: 1.15; font-weight: 700; }
h2 { font-size: 12.5pt; color: var(--navy); margin: 16px 0 6px; padding-left: 8px;
     border-left: 4px solid var(--teal); }
h3 { font-size: 10.3pt; color: var(--navy); margin: 11px 0 4px; }
h2, h3 { page-break-after: avoid; }
a { color: var(--teal); text-decoration: none; }
strong { color: #10263d; }
hr { border: none; border-top: 1px solid var(--line); margin: 14px 0; }
ul, ol { margin: 4px 0 8px; padding-left: 18px; }
li { margin: 2px 0; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 10px; font-size: 8.2pt;
        page-break-inside: avoid; }
th { background: var(--navy); color: #fff; font-weight: 600; text-align: left; padding: 4px 5px; }
td { padding: 3px 5px; border-bottom: 1px solid var(--line); vertical-align: top; }
tr:nth-child(even) td { background: var(--soft); }
code { font-family: Consolas, monospace; font-size: 8.2pt; background: #eef2f6;
       padding: 0 3px; border-radius: 3px; }
pre { background: #0f2a44; color: #e6edf3; padding: 8px 10px; border-radius: 6px;
      font-size: 8pt; white-space: pre-wrap; page-break-inside: avoid; }
pre code { background: none; color: inherit; padding: 0; }
blockquote { background: #eaf7f5; border-left: 4px solid var(--teal); margin: 8px 0;
             padding: 6px 10px; border-radius: 0 6px 6px 0; color: #1d3b38; }
blockquote p:last-child { margin: 0; }
figure { margin: 10px 0 12px; page-break-inside: avoid; text-align: center; }
figure img { max-width: 100%; border: 1px solid var(--line); border-radius: 4px; }
figcaption { font-size: 8pt; color: var(--muted); margin-top: 3px; font-style: italic; }
figcaption b { color: var(--navy); font-style: normal; }


/* cover */
.cover { height: 262mm; position: relative; page-break-after: always; }
.cover .band { background: var(--navy); color: #fff; margin: -15mm -14mm 0; padding: 30mm 18mm 16mm;
               position: relative; overflow: hidden; }
.cover .band:after { content: ""; position: absolute; right: -40mm; top: -30mm; width: 120mm;
                     height: 120mm; border-radius: 50%; background: rgba(14,159,142,.25); }
.cover .tag { font-size: 8.5pt; letter-spacing: 2px; text-transform: uppercase; color: #8fd9cf; }
.cover h1 { color: #fff; font-size: 27pt; margin: 6px 0 10px; max-width: 150mm; position: relative; }
.cover .sub { font-size: 11pt; color: #cfdbe7; max-width: 150mm; position: relative; }
.cover .who { margin: 14mm 4mm 8mm; font-size: 10pt; color: var(--muted); }
.cover .who b { color: var(--navy); font-size: 13pt; display: block; margin-bottom: 2px; }
.kpis { display: grid; grid-template-columns: 1fr 1fr; gap: 6mm; margin: 0 4mm; }
.kpi { border: 1px solid var(--line); border-radius: 8px; padding: 5mm 6mm; background: #fff;
       border-top: 4px solid var(--teal); }
.kpi:nth-child(2) { border-top-color: var(--amber); }
.kpi:nth-child(3) { border-top-color: var(--navy); }
.kpi:nth-child(4) { border-top-color: #6c5ce7; }
.kpi .num { font-size: 24pt; font-weight: 700; color: var(--navy); line-height: 1; }
.kpi .lbl { font-size: 9pt; color: var(--muted); margin-top: 4px; }
.cover .bottom { position: absolute; bottom: 0; left: 4mm; right: 4mm; font-size: 8.5pt;
                 color: var(--muted); border-top: 1px solid var(--line); padding-top: 4mm; }
.cover .bottom b { color: var(--navy); }

/* at a glance */
.glance { page-break-after: always; }
.eyebrow { font-size: 8pt; letter-spacing: 2px; text-transform: uppercase; color: var(--teal);
           font-weight: 600; margin-bottom: 2px; }
.flow { display: flex; gap: 2.5mm; margin: 6px 0 12px; align-items: stretch; }
.step { flex: 1; background: var(--soft); border-radius: 6px; padding: 3mm; position: relative;
        border-top: 3px solid var(--teal); }
.step .n { font-size: 7.5pt; color: var(--teal); font-weight: 700; letter-spacing: 1px; }
.step .t { font-weight: 700; color: var(--navy); font-size: 9.5pt; margin: 1px 0 2px; }
.step .d { font-size: 7.9pt; color: var(--muted); line-height: 1.35; }
.cols { display: grid; grid-template-columns: 1.05fr 1fr; gap: 7mm; }
.bars { margin: 4px 0 8px; }
.bar-row { display: grid; grid-template-columns: 30mm 1fr 14mm; align-items: center; gap: 2mm;
           font-size: 8.2pt; margin: 3px 0; }
.bar { height: 9px; background: #e3e9ef; border-radius: 5px; overflow: hidden; }
.bar span { display: block; height: 100%; border-radius: 5px; background: #9aa9b8; }
.bar span.best { background: var(--teal); }
.bar-row .v { text-align: right; font-weight: 600; color: var(--navy); }
.metric-title { font-size: 8.6pt; font-weight: 600; color: var(--navy); margin-top: 8px; }
.findings li { margin: 4px 0; }
.callout { background: var(--navy); color: #e8eef4; border-radius: 8px; padding: 5mm 6mm; margin-top: 10px; }
.callout b { color: #8fd9cf; }

/* section openers */
.doc { page-break-before: always; }
.section-label { display: inline-block; background: var(--teal); color: #fff; font-size: 7.8pt;
                 font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase;
                 padding: 2px 8px; border-radius: 3px; margin-bottom: 6px; }
.doc > h1:first-of-type { border-bottom: 2px solid var(--navy); padding-bottom: 5px; }
"""


def embed_image(rel_path: str, max_width: int = 1200, quality: int = 36) -> str:
    img = Image.open(ROOT / rel_path).convert("RGB")
    if img.width > max_width:
        img = img.resize((max_width, round(img.height * max_width / img.width)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def prepare_markdown(text: str) -> str:
    """Small fixes so GitHub-flavoured markdown renders the same in python-markdown."""
    text = re.sub(r"\[([^\]]+)\]\((?:README|DATA|RESULTS|Recommendation)\.md\)", r"\1", text)
    text = re.sub(r"(?m)^There is also `Flock_Energy_REFIT_submission\.pdf`.*\n", "", text)
    text = re.sub(r"(?m)^(?![ \t]*(?:[*-]|\d+\.) )(\S.*)\n(?=[*-] |\d+\. )", r"\1\n\n", text)
    text = re.sub(r"(?m)^ {2,3}(?=\S)", "    ", text)
    text = re.sub(r"(?m)^(?! {4}[*-] )(.*\S.*)\n(?= {4}[*-] )", r"\1\n\n", text)
    return text


class FigureCounter:
    def __init__(self):
        self.n = 0

    def __call__(self, m):
        self.n += 1
        alt, src = m.group("alt"), m.group("src")
        return (f'<figure><img src="{embed_image(src)}" alt="">'
                f'<figcaption><b>Figure {self.n}.</b> {alt}</figcaption></figure>')


def render_doc(md_name: str, label: str, figs: FigureCounter) -> str:
    html = markdown.markdown(prepare_markdown((ROOT / md_name).read_text(encoding="utf-8")),
                             extensions=["tables", "fenced_code", "sane_lists"])
    html = re.sub(r'<p><img alt="(?P<alt>[^"]*)" src="(?P<src>figures/[^"]+)" ?/?></p>', figs, html)
    return f'<div class="doc"><div class="section-label">{label}</div>{html}</div>'


def headline_numbers() -> dict:
    m = pd.read_csv(OUT / "model_metrics_mean.csv", index_col=0)
    steps = pd.read_csv(OUT / "raw_h1_steps.csv")
    cycles = pd.read_csv(OUT / "wm_cycles.csv")
    final, off, how = (m.loc["xgboost_window+cycle_filter"], m.loc["always_off"],
                       m.loc["hour_of_week"])
    corr = float(steps.loc[steps.metric == "corr_ours", "value"].iloc[0])
    corr_raw = float(steps.loc[steps.metric == "corr_naive_raw", "value"].iloc[0])
    return {
        "corr": corr, "corr_raw": corr_raw,
        "cycles": len(cycles), "homes": cycles.house.nunique(),
        "recall": final.cycle_recall, "precision": final.cycle_precision,
        "daily": {"Always off": off.daily_kWh_MAE, "Weekly pattern": how.daily_kWh_MAE,
                  "My model": final.daily_kWh_MAE},
        "f1": {"Always off": off.F1, "Weekly pattern": how.F1, "My model": final.F1},
        "recall_bars": {"Always off": off.cycle_recall, "Weekly pattern": how.cycle_recall,
                        "My model": final.cycle_recall},
        "daily_gain": 1 - final.daily_kWh_MAE / off.daily_kWh_MAE,
    }


def bars(values: dict, fmt: str, lower_is_better: bool) -> str:
    top = max(values.values()) or 1
    best = min(values, key=values.get) if lower_is_better else max(values, key=values.get)
    rows = []
    for name, v in values.items():
        width = 100 * v / top
        cls = "best" if name == best else ""
        rows.append(f'<div class="bar-row"><div>{name}</div><div class="bar">'
                    f'<span class="{cls}" style="width:{width:.1f}%"></span></div>'
                    f'<div class="v">{format(v, fmt)}</div></div>')
    return '<div class="bars">' + "".join(rows) + "</div>"


def cover(k: dict, author: str, repo_url: str) -> str:
    repo = f'<a href="{repo_url}">{repo_url}</a>' if repo_url else ""
    return f"""
<div class="cover">
  <div class="band">
    <div class="tag">Flock Energy &middot; Data Science take-home</div>
    <h1>Finding the washing machine inside a smart-meter reading</h1>
    <div class="sub">Cleaning raw REFIT data, analysing how 12 UK homes do their washing, and
    estimating washing-machine use from the whole-house meter alone.</div>
  </div>
  <div class="who"><b>{author}</b>Data Science submission</div>
  <div class="kpis">
    <div class="kpi"><div class="num">{k['corr']:.3f}</div>
      <div class="lbl">correlation between my cleaned House 1 data and the official version
      (raw data as recorded: {k['corr_raw']:.2f})</div></div>
    <div class="kpi"><div class="num">{k['cycles']:,}</div>
      <div class="lbl">wash cycles detected and analysed across {k['homes']} homes</div></div>
    <div class="kpi"><div class="num">{k['recall']:.0%}</div>
      <div class="lbl">of washes detected in homes the model never saw during training</div></div>
    <div class="kpi"><div class="num">{k['daily_gain']:.0%}</div>
      <div class="lbl">lower daily washing-machine energy error than the best baseline</div></div>
  </div>
  <div class="bottom"><b>Code and full pipeline:</b> {repo}<br>
  Data: REFIT Electrical Load Measurements, University of Strathclyde (CC-BY 4.0)</div>
</div>"""


def glance(k: dict) -> str:
    steps = [
        ("01", "Clean", "Raw House 1: fixed a daylight-saving bug, merged overlapping files, "
                        "removed sensor error codes, flagged outages."),
        ("02", "Explore", f"{k['cycles']:,} washes in {k['homes']} homes: timing, length, "
                          "energy and peak compared."),
        ("03", "Model", "XGBoost on a &plusmn;30 min window of whole-house power, tested on "
                        "homes it never saw."),
        ("04", "Recommend", "Use it for patterns and customer groups, starting with moving "
                            "washes off-peak."),
    ]
    flow = "".join(f'<div class="step"><div class="n">{n}</div><div class="t">{t}</div>'
                   f'<div class="d">{d}</div></div>' for n, t, d in steps)
    return f"""
<div class="glance">
  <div class="eyebrow">At a glance</div>
  <h1>What I did and what I found</h1>
  <p><b>The question.</b> Utilities see a home's total electricity use but not what each
  appliance is doing. Can we tell when the washing machine runs, and how much energy it uses,
  from the whole-house meter alone?</p>
  <div class="flow">{flow}</div>
  <div class="cols">
    <div>
      <h3>Key findings</h3>
      <ul class="findings">
        <li><b>The raw data was an hour out every summer.</b> The older raw file stored UK local
        time as if it were UTC. Fixing that took agreement with the official cleaned data from
        {k['corr_raw']:.2f} to {k['corr']:.3f}.</li>
        <li><b>The dataset's own "Issues" flag would have deleted the washes.</b> It fires on
        17&ndash;47% of minutes while a washing machine runs, so I didn't use it to drop data.</li>
        <li><b>A wash is a ~2 kW heating block plus a long quiet tail.</b> Peak power is almost
        identical across homes; energy per wash varies threefold with the programme chosen.</li>
        <li><b>Washing is concentrated in the morning peak.</b> 44% of washes start between 7am
        and noon. Two homes already use delay timers to wash at night.</li>
        <li><b>The model learns what a wash looks like, not when people wash.</b> Removing
        time-of-day features barely changes the results.</li>
      </ul>
    </div>
    <div>
      <h3>Results on unseen homes (12-fold, leave one house out)</h3>
      <div class="metric-title">Washes detected (higher is better)</div>
      {bars(k['recall_bars'], '.0%', lower_is_better=False)}
      <div class="metric-title">Minute-by-minute F1 (higher is better)</div>
      {bars(k['f1'], '.2f', lower_is_better=False)}
      <div class="metric-title">Daily energy error, kWh/day (lower is better)</div>
      {bars(k['daily'], '.2f', lower_is_better=True)}
      <div class="callout"><b>Recommendation.</b> Ready for pattern-based insights and
      customer grouping, such as nudging peak-time washers to use the delay timer, tested with
      a randomised trial. Not yet for exact per-home kWh: about {1 - k['precision']:.0%} of
      predicted washes are other heating appliances.</div>
    </div>
  </div>
  <h3>The model in action</h3>
  <figure><img src="{embed_image('figures/p3_actual_vs_pred_h15.png')}" alt="">
  <figcaption>House 15 was never seen in training. From the whole-house signal (grey) alone, the
  model's estimate (orange) finds the wash and its 2 kW heating block at the right time, and
  ignores the larger 3 kW load in the evening (blue = the real washing machine).</figcaption></figure>
</div>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-url", default="")
    ap.add_argument("--author", default="Arpit Thakur")
    ap.add_argument("--out", default=str(ROOT / "Arpit_Thakur_Flock_Energy_Assignment.pdf"))
    args = ap.parse_args()

    k = headline_numbers()
    figs = FigureCounter()
    body = [cover(k, args.author, args.repo_url), glance(k)]
    body += [render_doc(name, f"{i:02d} &middot; {label}", figs)
             for i, (name, label) in enumerate(DOCS, start=1)]
    html = (f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head>"
            f"<body>{''.join(body)}</body></html>")

    html_path = ROOT / "tools" / "_report.html"
    html_path.write_text(html, encoding="utf-8")
    browser = next((b for b in BROWSERS if Path(b).exists() or shutil.which(b)), None)
    if browser is None:
        raise SystemExit("Edge/Chrome not found; open tools/_report.html and print to PDF.")
    out = Path(args.out).resolve()
    subprocess.run([browser, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={out}", html_path.resolve().as_uri()],
                   check=True, capture_output=True, timeout=180)
    html_path.unlink()
    print(f"{out} ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
