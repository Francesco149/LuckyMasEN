@echo off
REM lm.cmd — drive the らき☆マス launcher on XP. The SYGNAS install dir is JP-named, which
REM breaks start/cd in cmd; so `setup` copies the launcher to an ASCII path (C:\lm) and points
REM Launch.ini at it, then everything runs from C:\lm with no JP-path pain. The calendar account
REM (gcal.ini) + gcalcore.dll come along in the copy; [Calendar] Boot=1 auto-checks on launch.
for /d %%i in ("C:\Program Files\SYGNAS\*") do set "SRC=%%~si\launcher"
set "LM=C:\lm"

if "%1"=="state" goto state
if "%1"=="setup" goto setup
if "%1"=="run"   goto run
if "%1"=="boot"  goto boot
if "%1"=="shot"  goto shot
if "%1"=="kill"  goto kill
echo usage: lm.cmd state^|setup^|run^|boot^|shot^|kill
goto :eof

:run
REM nircmd exec fully detaches (no inherited agent pipe -> no wedge); full ASCII path
REM so it resolves, cwd=C:\lm so Launch.exe can LoadLibrary gcalcore.dll.
cd /d "%LM%"
C:\probe\nircmd.exe exec show "%LM%\Launch.exe"
goto :eof

:state
echo SRC=%SRC%
dir /b "%SRC%\Launch.exe" "%SRC%\gcal.ini" 2>nul
echo --gcal.ini--
type "%SRC%\gcal.ini" 2>nul
echo --C:\lm--
dir /b "%LM%\Launch.exe" "%LM%\Launch.ini" 2>nul
goto :eof

:setup
rd /s /q "%LM%" 2>nul
xcopy "%SRC%" "%LM%\" /E /I /Y >nul
(
echo [Window]
echo X=480
echo Y=110
echo TopMost=1
echo [Data]
echo Chara=hiyori.Xvi
echo Folder=%LM%
echo [Calendar]
echo Boot=1
echo [Mail]
echo Boot=0
) > "%LM%\Launch.ini"
echo setup done:
dir /b "%LM%\Launch.exe" "%LM%\gcalcore.dll" "%LM%\gcal.ini" "%LM%\hiyori.Xvi"
goto :eof

:boot
REM start = visible on the interactive desktop (the agent wedges since Launch.exe holds
REM its pipe, but this batch keeps running server-side + takes the shots). ping WITHOUT
REM >nul so nircmd keeps a real stdout. Shots late (the mascot/bubble appears ~30s+ in).
cd /d "%LM%"
start "" "%LM%\Launch.exe"
ping -n 31 127.0.0.1
C:\probe\nircmd.exe savescreenshotfull "C:\gcal-xp\shotA.png"
ping -n 13 127.0.0.1
C:\probe\nircmd.exe savescreenshotfull "C:\gcal-xp\shotB.png"
ping -n 13 127.0.0.1
C:\probe\nircmd.exe savescreenshotfull "C:\gcal-xp\shotC.png"
goto :eof

:shot
REM nircmd savescreenshotfull's BitBlt does NOT capture the launcher's per-pixel-alpha
REM layered mascot window — it comes out as bare desktop. PrtScn -> clipboard grabs the
REM composited framebuffer (mascot included). VK 0x2c = PrtScn.
C:\probe\nircmd.exe sendkeypress 0x2c
ping -n 2 127.0.0.1
C:\probe\nircmd.exe clipboard saveimage "C:\gcal-xp\shot.png"
goto :eof

:kill
taskkill /f /im Launch.exe 2>nul
taskkill /f /im gcal.exe 2>nul
goto :eof
