@echo off
:: ============================================================
::  SAINHE — Backfill nuitier (03:30 AM)
::  Étend l'historique de 30 jours en arrière par ticker.
::  Cible : 7 ans. Après ~85 nuits (≈ 3 mois) : objectif atteint.
::  Durée estimée : 35-40 min (103 tickers × ~20s pause)
:: ============================================================
setlocal

set "PROJ=%~dp0.."
cd /d "%PROJ%"

set "LOG_DIR=%PROJ%\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
set "LOGFILE=%LOG_DIR%\backfill_%date:~-4%-%date:~3,2%-%date:~0,2%.log"

echo. >> "%LOGFILE%"
echo ======================================= >> "%LOGFILE%"
echo [%date% %time%] BACKFILL DEMARRAGE >> "%LOGFILE%"
echo ======================================= >> "%LOGFILE%"

echo [%time%] fetch_prices backfill (cible 7 ans, +30j/ticker) >> "%LOGFILE%"
py scripts\fetch_prices.py --mode backfill >> "%LOGFILE%" 2>&1
if errorlevel 1 echo [%time%] WARNING: backfill returned error >> "%LOGFILE%"

echo [%date% %time%] BACKFILL TERMINE >> "%LOGFILE%"
endlocal
