@echo off
for /f "tokens=5" %%a in ('netstat -ano ^| find ":8070" ^| find "LISTENING"') do (
  echo Killing PID %%a
  taskkill /f /pid %%a 2>nul
)
echo Done
