@echo off
REM Image Generation Studio — one-click launcher (Windows)
cd /d "%~dp0"
if not exist .venv (
    echo Creating virtual environment...
    py -m venv .venv
)
call .venv\Scripts\activate.bat
echo Installing dependencies...
pip install -q -r requirements.txt
if not exist .env (
    echo Creating .env from template...
    copy .env.example .env >nul
)
echo.
echo Starting Image Generation Studio at http://127.0.0.1:5000
python -m web.app
