@echo off
chcp 65001 >nul
title HKY V2 - Baslatici
cd /d "%~dp0"

rem 8000 portu doluysa (ornegin HKY V4 calisiyorsa) backend baslayamaz; once kullaniciyi uyar.
netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul
if %errorlevel%==0 (
  echo [UYARI] 8000 portu baska bir uygulama tarafindan kullaniliyor ^(muhtemelen HKY V4^).
  echo Once o terminal penceresinde Ctrl+C ile durdurun, sonra bu dosyayi tekrar calistirin.
  echo.
  pause
  exit /b 1
)

if not exist "frontend\node_modules" (
  echo Frontend paketleri ilk kez kuruluyor...
  call npm --prefix frontend install
)

start "HKY V2 - Backend (8000)" cmd /k python -m uvicorn app.main:app --reload --timeout-graceful-shutdown 3 --port 8000 --app-dir backend
start "HKY V2 - Frontend (5173)" cmd /k "cd /d frontend && npm run dev"

echo Sunucular baslatiliyor, tarayici birkac saniye icinde acilacak...
timeout /t 6 /nobreak >nul
start "" http://localhost:5173
