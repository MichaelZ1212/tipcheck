"""Copy only the files that belong on GitHub into a clean folder next to this project, for uploading
through the GitHub website (which, unlike git, does not read .gitignore).

    python scripts/export_for_github.py     ->  ../tipcheck_github/

Left out: .env (your key), .venv (installed packages), .git, caches, and run logs that aren't part of the
final evaluation. Included: code, README, sample data, eval results + their run logs, screenshots, report, slides.
"""

import csv
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parent / "tipcheck_github"
SKIP_DIRS = {".venv", ".git", "__pycache__", ".pytest_cache", "cache", "node_modules"}
SKIP_FILES = {".env", "spend.json", "tipcheck.zip"}

keep_runs = set()
results = ROOT / "data" / "eval" / "results.csv"
if results.exists():
    raw = results.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("gbk", errors="replace")
    keep_runs = {r["run_id"] + ".json" for r in csv.DictReader(text.splitlines())}

if OUT.exists():
    shutil.rmtree(OUT)
count = 0
for path in sorted(ROOT.rglob("*")):
    rel = path.relative_to(ROOT)
    if any(part in SKIP_DIRS for part in rel.parts) or path.is_dir():
        continue
    if path.name in SKIP_FILES or path.suffix in (".pyc", ".zip"):
        continue
    if rel.parts[:2] == ("data", "runs") and path.name not in keep_runs and path.name != ".gitkeep":
        continue
    dest = OUT / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)
    count += 1

leaked = [p for p in OUT.rglob("*") if p.name == ".env"]
if leaked:
    sys.exit("STOP: a .env file was copied. Do not upload. Tell Claude.")
print(f"Copied {count} files to {OUT}")
print("No .env included. Upload the CONTENTS of that folder on GitHub (Add file > Upload files).")
if count > 100:
    print("Note: GitHub's website takes 100 files per upload. Upload in two batches (e.g. 'data' first, then the rest).")
