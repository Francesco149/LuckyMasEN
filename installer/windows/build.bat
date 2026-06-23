@echo off
rem ===========================================================================
rem build.bat - the Windows front-door for the LuckyMasterEN self-service builder.
rem
rem   build.bat --setup D:\setup.exe --font auto
rem   build.bat --setup D:\setup.exe --font C:\Windows\Fonts\msgothic.ttc
rem
rem Produces out\LuckyMas-EN.iso (+ .zip) from YOUR LuckyMas disc's setup.exe and
rem YOUR own MS PGothic. Runs ISCC + innounp NATIVELY (no wine, no Docker).
rem
rem Zero manual install: it keeps a private Python under .\python (bootstrapped on
rem first run) so it never depends on a system Python or the Windows Store alias.
rem The freeware build tools (Inno Setup compiler, innounp, innoextract) are
rem pre-seeded in .\cache in the release bundle (else make_iso.py auto-downloads them).
rem ===========================================================================
setlocal EnableExtensions
cd /d "%~dp0..\.."
rem ^ this script lives in installer\windows\ ; the repo/bundle root is two levels up.

set "LUCKYMASEN_CACHE=%CD%\cache"
set "PYDIR=%CD%\python"
set "PY=%PYDIR%\python.exe"

rem 1) private Python (bootstrap on first run). We deliberately ignore any system
rem    Python / Store alias so behaviour is identical on every machine.
if not exist "%PY%" (
    echo No local Python yet - fetching a private copy into "%PYDIR%" ^(one-time^) ...
    call :bootstrap_python || goto :fail
)

rem 2) ensure the three Python deps are importable; install them into the private Python if not.
"%PY%" -c "import PIL, lief, pycdlib" 1>nul 2>nul
if errorlevel 1 (
    echo Installing Python dependencies ^(pillow, lief, pycdlib^) ...
    "%PY%" -m pip --version 1>nul 2>nul || "%PY%" "%PYDIR%\get-pip.py" --no-warn-script-location || goto :fail
    "%PY%" -m pip install --disable-pip-version-check --quiet pillow lief pycdlib || goto :fail
)

rem 3) run the shared engine.
echo.
"%PY%" tools\make_iso.py %*
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" ( echo Done. ) else ( echo Build failed ^(exit %RC%^). )
exit /b %RC%

:bootstrap_python
rem Heavy lifting lives in a .ps1 (robust quoting); build.bat stays thin.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap_python.ps1" "%PYDIR%"
if errorlevel 1 exit /b 1
exit /b 0

:fail
echo.
echo Setup failed. Need internet on first run to fetch Python + a few packages.
echo Or install Python 3.11+ yourself and run: python tools\make_iso.py --setup ... --font ...
echo See docs\end-user-build.md.
exit /b 1
