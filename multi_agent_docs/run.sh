#!/bin/bash
# Multi-Agent Code Analysis System - Startup Script
# Run: chmod +x run.sh && ./run.sh

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

if [ ! -f "$ROOT_DIR/.env" ]; then
    echo "No .env file found. Copying .env.example..."
    cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
    echo "Please edit .env and add your OPENAI_API_KEY, then run again."
    exit 1
fi

python3 --version > /dev/null 2>&1 || { echo "Python 3 not found"; exit 1; }
echo "Python: $(python3 --version)"

echo ""
echo "Installing backend dependencies..."
cd "$ROOT_DIR"
pip install -r backend/requirements.txt -q

echo "Installing frontend dependencies..."
pip install -r frontend/requirements.txt -q

mkdir -p data uploads chroma_db

echo ""
echo "Starting FastAPI backend on http://localhost:8000"
echo "   Swagger UI: http://localhost:8000/docs"
cd "$ROOT_DIR"
PYTHONPATH="$ROOT_DIR" uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

echo "Waiting for backend..."
sleep 4

if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "Backend is running!"
else
    echo "Backend may still be starting..."
fi

echo ""
echo "Starting Streamlit frontend on http://localhost:8501"
cd "$ROOT_DIR"
PYTHONPATH="$ROOT_DIR" streamlit run frontend/app.py \
    --server.port 8501 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --theme.base dark \
    --theme.primaryColor "#4361ee" \
    --theme.backgroundColor "#0e1117" \
    --theme.secondaryBackgroundColor "#1a1d27" \
    --theme.textColor "#e0e0e0" &
FRONTEND_PID=$!

echo ""
echo "Multi-Agent Code Analysis System"
echo "  Frontend:  http://localhost:8501"
echo "  Backend:   http://localhost:8000"
echo "  API Docs:  http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop all services"

wait $BACKEND_PID $FRONTEND_PID
