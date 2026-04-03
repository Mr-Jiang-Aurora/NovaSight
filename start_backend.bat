@echo off
title SOD/COD Backend (port 8000)
echo ============================================
echo  SOD/COD Research Assistant - Backend
echo  Port: 8000
echo  API docs: http://localhost:8000/docs
echo ============================================

REM Kill any existing instances on 8000
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000.*LISTENING" 2^>nul') do (
    echo Stopping existing process %%a on port 8000...
    taskkill /F /PID %%a 2>nul
)
timeout /t 1 /nobreak >nul

cd /d "d:\PycCharm Code\COD SOD Agent\sod_cod_assistant"

REM Try Anaconda Python first, then fall back to system python
set PYTHON_EXE=python
if exist "D:\Anaconda\anaconda3\python.exe" set PYTHON_EXE=D:\Anaconda\anaconda3\python.exe
if exist "C:\Users\Jzs\anaconda3\python.exe" set PYTHON_EXE=C:\Users\Jzs\anaconda3\python.exe
if exist "C:\ProgramData\Anaconda3\python.exe" set PYTHON_EXE=C:\ProgramData\Anaconda3\python.exe

echo Using Python: %PYTHON_EXE%
echo.

%PYTHON_EXE% fastapi_server.py
pause
