@echo off
setlocal EnableDelayedExpansion
set ROOT=%~dp0
set VENV=%ROOT%.runtime\venv

if not exist "%VENV%\Scripts\python.exe" (
  echo [ISD] Creating local venv...
  py -3.11 -m venv "%VENV%"
  if errorlevel 1 (
    echo [ISD] Failed to create venv. Ensure Python 3.11 launcher is available.
    exit /b 1
  )
)

call "%VENV%\Scripts\activate.bat"
python -m pip install --upgrade pip

set WHEEL=
for %%f in ("%ROOT%wheels\ionospheric_scintillation_detection-*.whl") do set WHEEL=%%f
if "%WHEEL%"=="" (
  echo [ISD] Wheel not found in %ROOT%wheels
  exit /b 1
)

echo [ISD] Installing %WHEEL%
python -m pip install "%WHEEL%"
if exist "%ROOT%requirements-win.txt" (
  python -m pip install -r "%ROOT%requirements-win.txt"
)

echo [ISD] Launching app...
python -m isd
