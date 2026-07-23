#!/bin/bash
# Double-clickable macOS launcher for the Agentic Playground.
# Creates the venv on first run, installs dependencies, starts the
# server, and opens the app in the default browser.
set -e
cd "$(dirname "$0")"

if [ ! -d venv ]; then
  echo "First run — creating virtual environment..."
  python3 -m venv venv
fi
source venv/bin/activate

echo "Checking dependencies..."
pip install -q -r requirements.txt

if [ ! -f .env ]; then
  echo ""
  echo "⚠  No .env file found. Copying .env.example — add your API keys to .env"
  echo "   (NEBIUS_API_KEY at minimum) and run this again."
  cp .env.example .env
  open -t .env 2>/dev/null || true
  exit 1
fi

PORT="${PORT:-8000}"
URL="http://localhost:${PORT}"

# Give the server a moment to boot, then open the browser.
( sleep 2; open "$URL" 2>/dev/null || xdg-open "$URL" 2>/dev/null || true ) &

echo "Starting Agentic Playground on ${URL} (Ctrl+C to stop)..."
PORT="$PORT" exec withkeys @first-agentic -- python app.py
