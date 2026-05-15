@echo off
set ROOT=%~dp0
set VENV=%ROOT%.runtime\venv
if not exist "%VENV%\Scripts\python.exe" (
  echo [ISD] Runtime not initialized. Run install_and_launch.bat first.
  exit /b 1
)
call "%VENV%\Scripts\activate.bat"
python -m isd
