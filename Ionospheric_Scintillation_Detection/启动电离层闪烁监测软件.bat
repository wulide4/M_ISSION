@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONPATH=%cd%\src;%PYTHONPATH%
echo Starting Ionospheric Scintillation Detection...
python -m isd.__main__
if errorlevel 1 (
    echo.
    echo Application exited with error code: %errorlevel%
    pause
)
