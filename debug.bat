@echo off
title SondeR cat debug
set "DEST=%LOCALAPPDATA%\SondeRcat"
if exist "%DEST%\sondercat\sondercat.py" (
  py -3 "%DEST%\sondercat\sondercat.py" 2>nul || python "%DEST%\sondercat\sondercat.py"
) else (
  py -3 "%~dp0sondercat.py" 2>nul || python "%~dp0sondercat.py"
)
echo.
echo (any error above is what to screenshot)
pause
