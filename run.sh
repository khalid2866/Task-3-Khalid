#!/usr/bin/env bash
# Image Generation Studio — one-click launcher (macOS / Linux)
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
echo "Installing dependencies..."
pip install -q -r requirements.txt
if [ ! -f .env ]; then
    echo "Creating .env from template..."
    cp .env.example .env
fi
echo ""
echo "Starting Image Generation Studio at http://127.0.0.1:5000"
python -m web.app
