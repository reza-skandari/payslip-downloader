#!/usr/bin/env bash
set -e

REPO="https://github.com/reza-skandari/payslip-downloader.git"
DIR="payslip-downloader"

# Clone if not already present
if [ ! -d "$DIR" ]; then
    echo "Cloning repository..."
    git clone "$REPO" "$DIR"
fi

cd "$DIR"

# Create venv if not already present
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

echo "Installing dependencies..."
pip install --quiet -r requirements.txt
pip install --quiet requests

# Install Playwright browsers on first run
if [ ! -d "$HOME/.cache/ms-playwright" ]; then
    echo "Downloading Chromium (first run only, ~150 MB)..."
    playwright install chromium
fi

echo "Starting app..."
python3 gui.py
