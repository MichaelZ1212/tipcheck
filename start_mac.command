#!/bin/bash
# Double-click to start TipCheck on a Mac. First run installs everything (2-3 minutes).
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed. Get it from https://www.python.org/downloads/ and double-click this file again."
  read -p "Press Enter to close."; exit 1
fi
if [ ! -f .env ] && [ ! -f ../.env ]; then
  cp .env.example .env
  echo "Created .env. Paste your key after PORTKEY_API_KEY= , save, close the editor, then double-click this file again."
  open -e .env
  read -p "Press Enter to close."; exit 0
fi
if [ ! -d .venv ]; then
  echo "First run: installing (2-3 minutes)..."
  python3 -m venv .venv || { read -p "Could not create .venv. Press Enter to close."; exit 1; }
  .venv/bin/pip install -q -r requirements.txt || { read -p "Install failed (see above). Press Enter to close."; exit 1; }
fi
.venv/bin/python run.py
