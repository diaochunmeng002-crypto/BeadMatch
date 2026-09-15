@echo off
rem ===================================================================
rem  BeadMatch - build a Windows exe (run this from the repo root)
rem  Output: dist\BeadMatch\BeadMatch.exe
rem  (messages are in English on purpose: cmd + Chinese needs chcp
rem   tricks and can end up as mojibake)
rem ===================================================================
setlocal
cd /d "%~dp0"

echo [1/4] Working dir: %cd%
where python >nul 2>nul
if errorlevel 1 goto nopython

echo [2/4] Checking build tools...
python -c "import PyInstaller" >nul 2>nul
if errorlevel 1 goto noinstall

python -c "import webview" >nul 2>nul
if errorlevel 1 goto noinstall

echo [3/4] Building (this takes a minute or two)...
python -m PyInstaller --noconfirm --onedir --noconsole --name BeadMatch ^
  --icon "beadmatch.ico" ^
  --add-data "web;web" ^
  --add-data "puzzles;puzzles" ^
  --paths "solver" ^
  --hidden-import free_solver ^
  --exclude-module numpy ^
  --exclude-module PIL ^
  --exclude-module cryptography ^
  --exclude-module pandas ^
  --exclude-module matplotlib ^
  --exclude-module streamlit ^
  --exclude-module tkinter ^
  --hidden-import uvicorn.logging ^
  --hidden-import uvicorn.loops.auto ^
  --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.websockets.auto ^
  --hidden-import uvicorn.lifespan.on ^
  launcher.py
if errorlevel 1 goto buildfail

echo [4/4] Done.
echo.
echo   Program : %cd%\dist\BeadMatch\BeadMatch.exe
echo   Data dir: same folder as the exe (puzzles\ and BeadMatch.log live there)
echo.
pause
exit /b 0

:nopython
echo ERROR: python not found in PATH. Install Python 3.11+ first.
pause
exit /b 1

:noinstall
echo Missing build tools. Install them with:
echo.
echo     python -m pip install pyinstaller pywebview
echo.
pause
exit /b 1

:buildfail
echo ERROR: PyInstaller failed. See the output above.
pause
exit /b 1
