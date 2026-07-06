@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" "sondercat.py"
) else (
  where py >nul 2>nul && (py sondercat.py) || (python sondercat.py)
)
