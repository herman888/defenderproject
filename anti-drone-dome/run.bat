@echo off
REM ============================================================
REM  Anti-Drone Dome - one-click launcher
REM  Double-click this file, or run:  run.bat <mode>
REM  modes: sim | swarm | overwhelm | swarm3d | test | docs
REM ============================================================
setlocal
cd /d "%~dp0"

REM --- locate a Python interpreter ----------------------------
set "PY="
if exist ".venv\Scripts\python.exe"   set "PY=.venv\Scripts\python.exe"
if not defined PY if exist "venv312\Scripts\python.exe" set "PY=venv312\Scripts\python.exe"
if not defined PY where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo.
  echo   Could not find Python. Install Python 3.12, or create the venv:
  echo     python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

REM --- one-shot mode from the command line --------------------
if not "%~1"=="" (
  call :run %1
  exit /b %errorlevel%
)

:menu
cls
echo ============================================================
echo    ANTI-DRONE DOME   -   launcher
echo ============================================================
echo    Python: %PY%
echo.
echo    [1]  Command center        (full interactive simulation)
echo    [2]  Swarm demo            (6 threats vs 4 interceptors)
echo    [3]  Swarm overwhelm       (8 threats vs 3 interceptors)
echo    [4]  Swarm in 3D           (PyBullet headless engagement)
echo    [5]  Swarm LIVE in C2      (watch the swarm in the command center)
echo    [6]  Run tests
echo    [7]  Build docs (strict)
echo    [0]  Quit
echo.
set "choice="
set /p choice="  Choose a number and press Enter: "

if "%choice%"=="1" ( call :run sim       & goto after )
if "%choice%"=="2" ( call :run swarm     & goto after )
if "%choice%"=="3" ( call :run overwhelm & goto after )
if "%choice%"=="4" ( call :run swarm3d   & goto after )
if "%choice%"=="5" ( call :run swarmlive & goto after )
if "%choice%"=="6" ( call :run test      & goto after )
if "%choice%"=="7" ( call :run docs      & goto after )
if "%choice%"=="0" ( exit /b 0 )
goto menu

:after
echo.
echo ------------------------------------------------------------
pause
goto menu

REM --- command map --------------------------------------------
:run
if /i "%~1"=="sim"       ( %PY% main.py & goto :eof )
if /i "%~1"=="swarm"     ( %PY% swarm\runner.py --scenario saturation_6v4 --seed 42 & goto :eof )
if /i "%~1"=="overwhelm" ( %PY% swarm\runner.py --scenario overwhelm_8v3 --seed 7 & goto :eof )
if /i "%~1"=="swarm3d"   ( %PY% main.py --swarm saturation_6v4 & goto :eof )
if /i "%~1"=="swarmlive"  ( %PY% main.py --swarm-live saturation_6v4 & goto :eof )
if /i "%~1"=="test"      ( %PY% -m pytest -q & goto :eof )
if /i "%~1"=="docs"      ( %PY% -m mkdocs build --strict & goto :eof )
echo   Unknown mode "%~1". Use: sim ^| swarm ^| overwhelm ^| swarm3d ^| swarmlive ^| test ^| docs
goto :eof
