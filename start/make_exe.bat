@echo off
rem ===================================================================
rem  BeadMatch - build a Windows exe (run this from the repo root)
rem  Output: dist\BeadMatch\BeadMatch.exe
rem  (messages are in English on purpose: cmd + Chinese needs chcp
rem   tricks and can end up as mojibake)
rem ===================================================================
setlocal
rem 脚本在 start\ 下，但所有相对路径都是相对仓库根目录的 —— 先退到上一级
cd /d "%~dp0.."

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
  --icon "%cd%\start\beadmatch.ico" ^
  --paths "%cd%" ^
  --specpath "build" ^
  --add-data "%cd%\games\beadmatch\web;games/beadmatch/web" ^
  --add-data "%cd%\games\beadmatch\puzzles;games/beadmatch/puzzles" ^
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
  "%cd%\start\launcher.py"
if errorlevel 1 goto buildfail

echo [4/4] Done.
echo.
echo   Program : %cd%\dist\BeadMatch\BeadMatch.exe
echo   Data dir: same folder as the exe (games\beadmatch\puzzles and BeadMatch.log live there)
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
