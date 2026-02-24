@echo off
echo === AURORA 0.01%% === Autonomous AI Sales Agent ===

:: Check if .env exists
if not exist backend\.env (
    echo.
    echo [ERROR] backend\.env not found!
    echo Please copy .env.example to backend\.env and fill in your keys.
    echo.
    pause
    exit /b 1
)

:: Start backend in new terminal
echo Starting FastAPI backend on :8000 ...
start "AURORA Backend" cmd /k "cd backend && .venv\Scripts\activate && uvicorn main:app --reload --port 8000"

:: Wait a moment
timeout /t 3 /nobreak > nul

:: Start dashboard in new terminal
echo Starting Streamlit dashboard on :8501 ...
start "AURORA Dashboard" cmd /k "cd dashboard && streamlit run dashboard.py"

:: Start landing page
echo Starting Next.js landing page on :3000 ...
start "AURORA Landing" cmd /k "cd landing && npm run dev"

echo.
echo =========================================
echo  AURORA is running:
echo   Backend:   http://localhost:8000/docs
echo   Dashboard: http://localhost:8501
echo   Landing:   http://localhost:3000
echo =========================================
echo.
pause
