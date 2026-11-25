@echo off
setlocal
cd /d "%~dp0"

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "skills\kline-chart\scripts\desktop_app.py" %*
    exit /b 0
)

where python >nul 2>nul
if %errorlevel%==0 (
    python "skills\kline-chart\scripts\desktop_app.py" %*
    if not %errorlevel%==0 pause
    exit /b %errorlevel%
)

echo [ERROR] Python not found in PATH. Please install Python 3.10+.
pause
exit /b 1
