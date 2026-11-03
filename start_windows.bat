@echo off
set PYTHONUTF8=1
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    where py >nul 2>nul
    if errorlevel 1 (
        python -m venv .venv
    ) else (
        py -3 -m venv .venv
    )
    if errorlevel 1 goto :error
)
.venv\Scripts\python.exe -m pip install -e ".[contacts]"
if errorlevel 1 goto :error
.venv\Scripts\python.exe -m parser_toolkit gui
if errorlevel 1 goto :error
exit /b 0
:error
echo.
echo Could not start. Install Python 3.11+ from python.org with "Add Python to PATH".
echo See README.ru.md for troubleshooting. Copy the error above if you need help.
pause
exit /b 1
