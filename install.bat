@echo off
setlocal EnableExtensions
title SondeR cat installer
echo.
echo    /\_/\     SondeR cat installer
echo   ( o.o )    everything included - no pip, no downloads needed
echo.
set "SRC=%~dp0"
set "DEST=%LOCALAPPDATA%\SondeRcat"

echo [..] Stopping any running cats...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -match 'sondercat' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1

echo [..] Looking for Python...
set "PY="
call :check "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
call :check "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
call :check "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
call :check "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
call :check "%LOCALAPPDATA%\Programs\Python\Python39\python.exe"
if defined PY goto havepy
for /f "delims=" %%P in ('where python 2^>nul') do call :check "%%P"
if defined PY goto havepy
for /f "delims=" %%P in ('where python3 2^>nul') do call :check "%%P"
if defined PY goto havepy
for /f "delims=" %%P in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do call :check "%%P"
if defined PY goto havepy

echo [..] Python not found - asking Windows' package manager to install it...
winget install -e --id Python.Python.3.12 --silent --scope user --accept-package-agreements --accept-source-agreements
call :check "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
for /f "delims=" %%P in ('where python 2^>nul') do call :check "%%P"
if defined PY goto havepy
echo.
echo [!] Couldn't find or install Python automatically.
echo     Please install "Python 3.12" from the Microsoft Store,
echo     then double-click me again.
pause
exit /b 1

:havepy
echo [OK] Using Python: %PY%

echo [..] Copying files...
robocopy "%SRC%." "%DEST%\sondercat" /E /NFL /NDL /NJH /NJS /XD libs .git .venv __pycache__ wheels /XF SondeR_cat_setup.exe *.zip >nul
if %errorlevel% GEQ 8 goto copyfail
if not exist "%SRC%libs" goto libsdone
robocopy "%SRC%libs" "%DEST%\libs" /E /NFL /NDL /NJH /NJS >nul
if %errorlevel% GEQ 8 goto copyfail
:libsdone

echo [..] Checking components...
"%PY%" -c "import sys;sys.path.insert(0,r'%DEST%\libs');import PySide6.QtWidgets,pynput" >nul 2>&1
if not %errorlevel%==0 goto healthfail

set "PYW=%PY:python.exe=pythonw.exe%"
if not exist "%PYW%" set "PYW=%PY%"

echo [..] Creating Desktop shortcut...
set "LNK=%USERPROFILE%\Desktop\SondeR cat.lnk"
powershell -NoProfile -Command "$q=[char]34;$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%LNK%');$s.TargetPath='%PYW%';$s.Arguments=$q+'%DEST%\sondercat\sondercat.py'+$q;$s.WorkingDirectory='%DEST%\sondercat';$s.IconLocation='%DEST%\sondercat\sondercat_gray.ico';$s.Save()" >nul 2>&1
if exist "%LNK%" goto lnkok
rem fallback launcher if shortcut creation was restricted
(
  echo @echo off
  echo start "" "%PYW%" "%DEST%\sondercat\sondercat.py"
) > "%USERPROFILE%\Desktop\SondeR cat.bat"
set "LNK=%USERPROFILE%\Desktop\SondeR cat.bat"
:lnkok

choice /C YN /N /M "Start SondeR cat automatically when Windows starts? [Y/N] "
if not %errorlevel%==1 goto nostartup
copy /Y "%LNK%" "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\" >nul 2>&1
:nostartup

echo.
echo [OK] Installed! Launching your cat...
start "" "%PYW%" "%DEST%\sondercat\sondercat.py"
timeout /t 2 >nul
exit /b 0

:check
if defined PY goto :eof
set "CAND=%~1"
if not exist "%CAND%" goto :eof
echo %CAND%| findstr /I "WindowsApps" >nul && goto :eof
"%CAND%" -c "import struct,sys;sys.exit(0 if struct.calcsize('P')==8 and sys.version_info>=(3,9) else 3)" >nul 2>&1
if %errorlevel%==0 set "PY=%CAND%"
goto :eof

:copyfail
echo.
echo [!] Couldn't copy files. If a SondeR cat is running, quit it
echo     (right-click the cat, Quit) and run me again.
pause
exit /b 1

:healthfail
echo.
echo [!] The bundled components failed to load with this Python.
echo     Tell the developer - include a screenshot of this window.
echo     Python used: %PY%
pause
exit /b 1
