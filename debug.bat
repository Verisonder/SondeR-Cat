@echo off
title SondeR cat (debug mode)
set "BASE=%~dp0"
if not exist "%BASE%sondercat.py" if exist "%BASE%sondercat\sondercat.py" set "BASE=%BASE%sondercat\"
if not exist "%BASE%sondercat.py" if exist "%BASE%sondercat\sondercat\sondercat.py" set "BASE=%BASE%sondercat\sondercat\"
cd /d "%BASE%"
echo Running SondeR cat with a visible console so errors show up...
echo Using files in: %BASE%
echo ==============================================================
if exist "%BASE%.venv\Scripts\python.exe" (
    "%BASE%.venv\Scripts\python.exe" sondercat.py
) else (
    where py >nul 2>nul && (py sondercat.py) || (python sondercat.py)
)
echo ==============================================================
echo If the cat crashed, the error above says why.
echo There may also be details in: %USERPROFILE%\sondercat_error.log
pause
