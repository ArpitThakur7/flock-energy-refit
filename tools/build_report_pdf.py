"""Combine README, DATA, RESULTS and Recommendation into one PDF for submission.

    python tools/build_report_pdf.py [--repo-url URL]

Figures are re-encoded as compressed JPEGs and embedded, so the PDF stays under
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
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DOCS = [("Recommendation.md", "Summary and recommendation"),
        ("README.md", "Overview, setup and design"),
        ("DATA.md", "Data, quality and cleaning"),
        ("RESULTS.md", "EDA, model results and failure analysis")]
BROWSERS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "msedge", "google-chrome", "chromium", "chrome"]

CSS = """
@page { size: A4; margin: 14mm 13mm; }
body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 9.3pt; line-height: 1.38; color: #1d1d1f; }
h1 { font-size: 17pt; color: #12355b; border-bottom: 2px solid #12355b; padding-bottom: 3px; margin: 0 0 8px; }
h2 { font-size: 12.5pt; color: #12355b; margin: 14px 0 5px; }
h3 { font-size: 10.5pt; margin: 10px 0 4px; }
table { border-collapse: collapse; width: 100%; margin: 6px 0; font-size: 8.2pt; page-break-inside: avoid; }
th, td { border: 1px solid #c9ced6; padding: 2.5px 4px; text-align: left; vertical-align: top; }
th { background: #eef2f7; }
code { font-family: Consolas, monospace; font-size: 8.3pt; background: #f3f4f6; padding: 0 2px; }
pre { background: #f3f4f6; padding: 6px; font-size: 8pt; white-space: pre-wrap; }
blockquote { border-left: 3px solid #9fb3c8; margin: 6px 0; padding: 2px 8px; color: #444; }
img { max-width: 100%; display: block; margin: 6px auto; page-break-inside: avoid; }
.doc { page-break-before: always; }
.cover { text-align: center; padding-top: 60mm; }
.cover h1 { border: none; font-size: 22pt; }
.cover p { font-size: 11pt; color: #444; }
.tag { font-size: 8pt; color: #777; text-transform: uppercase; letter-spacing: 1px; }
"""


def embed_image(rel_path: str, max_width: int = 1250, quality: int = 45) -> str:
    img = Image.open(ROOT / rel_path).convert("RGB")
    if img.width > max_width:
        img = img.resize((max_width, round(img.height * max_width / img.width)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def render_doc(md_name: str) -> str:
    text = (ROOT / md_name).read_text(encoding="utf-8")
    # Links to the other docs make no sense inside one PDF -> plain text.
    text = re.sub(r"\[([^\]]+)\]\((?:README|DATA|RESULTS|Recommendation)\.md\)", r"\1", text)
    # GitHub accepts a list straight after a paragraph line; python-markdown needs
    # a blank line first, otherwise the bullets are rendered inline.
    text = re.sub(r"(?m)^(?![ \t]*(?:[*-]|\d+\.) )(\S.*)\n(?=[*-] |\d+\. )", r"\1\n\n", text)
    # Nested bullets: python-markdown wants a 4-space indent and a blank line before.
    text = re.sub(r"(?m)^ {2,3}(?=\S)", "    ", text)
    text = re.sub(r"(?m)^(?! {4}[*-] )(.*\S.*)\n(?= {4}[*-] )", r"\1\n\n", text)
    html = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
    return re.sub(r'src="(figures/[^"]+)"', lambda m: f'src="{embed_image(m.group(1))}"', html)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-url", default="")
    ap.add_argument("--out", default=str(ROOT / "Flock_Energy_REFIT_submission.pdf"))
    args = ap.parse_args()

    repo_line = (f'<p>Code: <a href="{args.repo_url}">{args.repo_url}</a></p>'
                 if args.repo_url else "")
    parts = [f"""<div class="cover">
<p class="tag">Flock Energy - Data Science take-home</p>
<h1>REFIT data cleaning and washing-machine disaggregation</h1>
<p>Raw House 1 cleaning &middot; washing-machine EDA across 12 homes &middot;
seq2point-style XGBoost validated leave-one-house-out</p>
{repo_line}
<p style="margin-top:20mm;font-size:9.5pt;text-align:left;display:inline-block">
Contents<br>1. {DOCS[0][1]}<br>2. {DOCS[1][1]}<br>3. {DOCS[2][1]}<br>4. {DOCS[3][1]}</p>
</div>"""]
    for name, _ in DOCS:
        parts.append(f'<div class="doc">{render_doc(name)}</div>')
    html = f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{''.join(parts)}</body></html>"

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
