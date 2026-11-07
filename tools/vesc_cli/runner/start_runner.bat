@echo off
cd /d "%~dp0"
where python >nul 2>nul || (echo Python is not installed: get it from python.org, tick "Add to PATH" & pause & exit /b)
python -m pip install --quiet pyserial
python vesc_runner.py
pause
