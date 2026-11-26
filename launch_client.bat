@echo off
setlocal
cd /d "%~dp0"

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "skills\flowsurface\scripts\launch_flowsurface.py" %*
    exit /b 0
)

where python >nul 2>nul
if %errorlevel%==0 (
    python "skills\flowsurface\scripts\launch_flowsurface.py" %*
    if not %errorlevel%==0 pause
    exit /b %errorlevel%
)

echo [ERROR] Python not found in PATH. Please install Python 3.10+.
pause
exit /b 1
