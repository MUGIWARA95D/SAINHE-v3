@echo off
:: ============================================================
::  SAINHE — Pipeline nuitier principal (01:00 AM)
::  fetch_prices update + fx + macro + calc + render
::  Durée estimée : 50-60 min (103 tickers × ~20s pause)
:: ============================================================
setlocal

:: Répertoire projet (dossier parent de \scripts\)
set "PROJ=%~dp0.."
cd /d "%PROJ%"

:: Log fichier daté
set "LOG_DIR=%PROJ%\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
set "LOGFILE=%LOG_DIR%\pipeline_%date:~-4%-%date:~3,2%-%date:~0,2%.log"

echo. >> "%LOGFILE%"
echo ======================================= >> "%LOGFILE%"
echo [%date% %time%] PIPELINE DEMARRAGE >> "%LOGFILE%"
echo ======================================= >> "%LOGFILE%"

:: Charger .env si présent (FRED_API_KEY, GDRIVE_*)
if exist "%PROJ%\.env" (
    for /f "usebackq tokens=1,* delims==" %%A in ("%PROJ%\.env") do (
        if not "%%A"=="" if not "%%A:~0,1%"=="#" set "%%A=%%B"
    )
)

:: ── ÉTAPE 1 — Fetch prix (moitié A) ─────────────────────────
echo [%time%] STEP 1/6 fetch_prices half=0 >> "%LOGFILE%"
py scripts\fetch_prices.py --mode update --half 0 >> "%LOGFILE%" 2>&1
if errorlevel 1 echo [%time%] WARNING: fetch_prices half=0 returned error >> "%LOGFILE%"

:: ── ÉTAPE 2 — Fetch prix (moitié B) ─────────────────────────
echo [%time%] STEP 2/6 fetch_prices half=1 >> "%LOGFILE%"
py scripts\fetch_prices.py --mode update --half 1 >> "%LOGFILE%" 2>&1
if errorlevel 1 echo [%time%] WARNING: fetch_prices half=1 returned error >> "%LOGFILE%"

:: ── ÉTAPE 3 — Taux de change ─────────────────────────────────
echo [%time%] STEP 3/6 fetch_fx >> "%LOGFILE%"
py scripts\fetch_fx.py >> "%LOGFILE%" 2>&1
if errorlevel 1 echo [%time%] WARNING: fetch_fx returned error >> "%LOGFILE%"

:: ── ÉTAPE 4 — Indicateurs macro/liquidité (FRED) ─────────────
echo [%time%] STEP 4/6 fetch_macro_liquidity >> "%LOGFILE%"
py scripts\fetch_macro_liquidity.py >> "%LOGFILE%" 2>&1
if errorlevel 1 echo [%time%] WARNING: fetch_macro_liquidity returned error >> "%LOGFILE%"

:: ── ÉTAPE 5 — Calcul snapshot + métriques ────────────────────
echo [%time%] STEP 5/6 calc >> "%LOGFILE%"
py scripts\calc.py >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    echo [%time%] ERROR: calc.py failed - render aborted >> "%LOGFILE%"
    goto :end
)

:: ── ÉTAPE 6 — Rendu HTML ─────────────────────────────────────
echo [%time%] STEP 6/6 render_html >> "%LOGFILE%"
py render_html.py >> "%LOGFILE%" 2>&1
if errorlevel 1 echo [%time%] WARNING: render_html returned error >> "%LOGFILE%"

:: ── OPTIONNEL — Sync Google Drive (si GDRIVE_FILE_ID dispo) ──
if defined GDRIVE_FILE_ID (
    echo [%time%] gdrive_sync upload >> "%LOGFILE%"
    py scripts\gdrive_sync.py upload >> "%LOGFILE%" 2>&1
)

:end
echo [%date% %time%] PIPELINE TERMINE >> "%LOGFILE%"
endlocal
