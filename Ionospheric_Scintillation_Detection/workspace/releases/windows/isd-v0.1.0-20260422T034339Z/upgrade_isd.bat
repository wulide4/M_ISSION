@echo off
set ROOT=%~dp0
set VENV=%ROOT%.runtime\venv
if not exist "%VENV%\Scripts\python.exe" (
  echo [ISD] Runtime not initialized. Run install_and_launch.bat first.
  exit /b 1
)
call "%VENV%\Scripts\activate.bat"
set WHEEL=
for %%f in ("%ROOT%wheels\ionospheric_scintillation_detection-*.whl") do set WHEEL=%%f
if "%WHEEL%"=="" (
  echo [ISD] Wheel not found in %ROOT%wheels
  exit /b 1
)
python -m pip install --upgrade "%WHEEL%"
echo [ISD] Upgrade completed. Starting app once to apply migrations...
python -m isd
