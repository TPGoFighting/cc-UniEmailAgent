@echo off
echo ==========================================
echo  UniEmail Agent Backend Restarter (Windows)
echo ==========================================
echo.

echo 1. Detecting and freeing port 8000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
    echo Found process occupying port 8000 with PID: %%a, terminating...
    taskkill /F /PID %%a >nul 2>&1
)

echo 2. Terminating stray uvicorn/python processes...
taskkill /F /IM uvicorn.exe >nul 2>&1

echo 3. Launching FastAPI backend server...
cd /d "%~dp0\backend"
start "UniEmail-Backend" /min python -m uvicorn main:app --port 8000 --reload

echo.
echo [SUCCESS] Backend server started successfully in the background!
echo [INFO] Listening on: http://127.0.0.1:8000
echo ==========================================
timeout /t 3 > nul
