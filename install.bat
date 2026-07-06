@echo off
setlocal EnableExtensions
title SondeR cat installer
cd /d "%~dp0"

echo.
echo    /\_/\     SondeR cat installer
echo   ( o.o )    =====================
echo    ^> ^^ ^<     This sets up everything for you.
echo.

rem --------------------------------------- locate the cat's files ----------
set "BASE=%~dp0"
if not exist "%BASE%sondercat.py" if exist "%BASE%sondercat\sondercat.py" set "BASE=%BASE%sondercat\"
if not exist "%BASE%sondercat.py" if exist "%BASE%sondercat\sondercat\sondercat.py" set "BASE=%BASE%sondercat\sondercat\"
if not exist "%BASE%sondercat.py" (
    echo [!] I can't find sondercat.py near this installer.
    echo     Make sure you EXTRACTED the whole zip ^(not just opened it^)
    echo     and keep install.bat together with sondercat.py.
    echo.
    echo     I looked in:
    echo       %~dp0
    echo       %~dp0sondercat\
    echo.
    pause
    exit /b 1
)
echo Using files in: %BASE%

rem ---------------------------------------------------------- find python ---
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"

if not defined PY (
    echo [1/5] Python is not installed. Trying to install it with winget...
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    echo.
    echo If Python just got installed, please CLOSE this window and
    echo run install.bat once more so Windows can find it.
    echo If winget failed, install Python from the page that opens
    echo ^(check "Add python.exe to PATH"^) and re-run install.bat.
    start https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [1/5] Found Python.

echo       Stopping any running SondeR cat first...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -match 'sondercat' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

rem ------------------------------------------------------------- make venv --
echo [2/5] Creating a private environment (.venv)...
if exist "%BASE%.venv\Scripts\python.exe" (
    echo       Found an existing one - reusing it.
) else (
    %PY% -m venv "%BASE%.venv"
)
if not exist "%BASE%.venv\Scripts\python.exe" (
    echo       First attempt failed - cleaning up and retrying...
    rmdir /s /q "%BASE%.venv" >nul 2>&1
    %PY% -m venv "%BASE%.venv"
)
if not exist "%BASE%.venv\Scripts\python.exe" (
    echo Could not create the environment.
    echo If a SondeR cat is running right now, quit it ^(right-click the cat^)
    echo and run this installer again.
    pause & exit /b 1
)
set "VPY=%BASE%.venv\Scripts\python.exe"
set "VPYW=%BASE%.venv\Scripts\pythonw.exe"

echo [3/5] Installing the cat's dependencies (this can take a minute)...
"%VPY%" -m pip install --upgrade pip --quiet
if exist "%BASE%requirements.txt" (
    "%VPY%" -m pip install -r "%BASE%requirements.txt" --quiet
) else (
    echo     ^(requirements.txt not found - installing packages directly^)
    "%VPY%" -m pip install "PySide6>=6.5" "pynput>=1.7" --quiet
)
if errorlevel 1 (
    echo Dependency install failed. Check your internet connection and retry.
    pause & exit /b 1
)

rem ------------------------------------------------------------ verify ------
echo [4/5] Checking that everything actually works...
"%VPY%" -c "import PySide6, pynput" 2>nul
if errorlevel 1 (
    echo [!] The libraries did not install correctly.
    echo     Delete the .venv folder here and run install.bat again.
    pause & exit /b 1
)
"%VPY%" -m py_compile "%BASE%sondercat.py" "%BASE%sprites.py"
if errorlevel 1 (
    echo [!] The app files look damaged. Re-extract the zip and retry.
    pause & exit /b 1
)
echo       All good!

rem -------------------------------------------------------------- shortcuts -
echo [5/5] Creating a Desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$s = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\SondeR cat.lnk');" ^
  "$s.TargetPath = '%VPYW%';" ^
  "$s.Arguments = 'sondercat.py';" ^
  "$s.WorkingDirectory = '%BASE%';" ^
  "$s.IconLocation = '%BASE%cat.ico';" ^
  "$s.Description = 'A pixel cat for your desktop';" ^
  "$s.Save()"

choice /c YN /m "Start SondeR cat automatically when Windows starts"
if errorlevel 2 goto :skipstartup
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$s = $ws.CreateShortcut($ws.SpecialFolders('Startup') + '\SondeR cat.lnk');" ^
  "$s.TargetPath = '%VPYW%';" ^
  "$s.Arguments = 'sondercat.py';" ^
  "$s.WorkingDirectory = '%BASE%';" ^
  "$s.IconLocation = '%BASE%cat.ico';" ^
  "$s.Save()"
echo Autostart enabled.
:skipstartup

echo.
echo  All done! Launching your cat...
echo  If it ever won't start, run "debug.bat" in this folder to see why.
echo.
start "" /D "%BASE%" "%VPYW%" sondercat.py
timeout /t 4 >nul
exit /b 0
