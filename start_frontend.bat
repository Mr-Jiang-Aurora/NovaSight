@echo off
title SOD/COD Frontend (production - port 3000)
echo ============================================
echo  SOD/COD Research Assistant - Frontend
echo  MODE: production (low memory ~200MB)
echo  URL:  http://localhost:3000
echo ============================================

cd /d "d:\PycCharm Code\COD SOD Agent\sod-cod-frontend"

REM Check if already built
if exist ".next\BUILD_ID" (
    echo Found existing build. Starting production server...
    echo.
    npx next start
) else (
    echo No build found. Building first (takes ~1 min)...
    set NODE_OPTIONS=--max-old-space-size=1024
    npx next build
    if errorlevel 1 (
        echo BUILD FAILED! See errors above.
        pause
        exit /b 1
    )
    echo Build done! Starting production server...
    npx next start
)
pause
