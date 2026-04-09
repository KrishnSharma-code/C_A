@echo off
REM Multi-Agent Code Analysis System - Windows Startup Script
REM Usage: Double-click run.bat or run from the project root folder

echo.
echo =====================================================
echo   Multi-Agent Code Analysis System
echo =====================================================
echo.

if not exist .env (
    echo No .env file found. Copying .env.example...
    copy .env.example .env
    echo Please edit .env and add your OPENAI_API_KEY, then run again.
    pause
    exit /b 1
)

echo Installing backend dependencies...
python -m pip install -r backend\requirements.txt

echo Installing frontend dependencies...
python -m pip install -r frontend\requirements.txt

if not exist data mkdir data
if not exist uploads mkdir uploads
if not exist chroma_db mkdir chroma_db

echo.
echo Starting FastAPI backend on http://localhost:8000
start "Backend" cmd /k "set PYTHONPATH=%CD% && python -m uvicorn backend.main:app --reload-dir backend --port 8000"

echo Waiting for backend to start...
python -c "import time; time.sleep(5)"

echo Starting Streamlit frontend on http://localhost:8502
start "Frontend" cmd /k "set PYTHONPATH=%CD% && python -m streamlit run frontend\app.py --server.port 8502"

echo.
echo =====================================================
echo   Frontend:  http://localhost:8502
echo   Backend:   http://localhost:8000
echo   API Docs:  http://localhost:8000/docs
echo =====================================================
echo.
pause
