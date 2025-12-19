@echo off
echo Starting NORTH AI Development Servers...
echo.
echo Starting Backend (FastAPI) on port 8000...
start "NORTH Backend" cmd /k "uvicorn api:app --reload --host 0.0.0.0 --port 8000"

echo Starting Frontend (React/Vite) on port 5173...
start "NORTH Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo ========================================
echo Servers are starting up...
echo.
echo Frontend: http://localhost:5173
echo Backend:  http://localhost:8000
echo.
echo Press any key to open the frontend in your browser...
pause >nul
start http://localhost:5173