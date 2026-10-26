@echo off
REM Double-click to start TipCheck on Windows. First run installs everything (2-3 minutes).
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python is not installed. Get it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^), then double-click this file again.
  pause & exit /b 1
)
if not exist .env if not exist ..\.env (
  copy .env.example .env >nul
  echo Created .env. Paste your key after PORTKEY_API_KEY= , save, close Notepad, then double-click this file again.
  notepad .env
  pause & exit /b 0
)
if not exist .venv (
  echo First run: installing ^(2-3 minutes^)...
  python -m venv .venv || (pause & exit /b 1)
  .venv\Scripts\python -m pip install -q -r requirements.txt || (echo Install failed, see above. & pause & exit /b 1)
)
.venv\Scripts\python run.py
pause
