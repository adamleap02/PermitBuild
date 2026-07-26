@echo off
REM ---------------------------------------------------------------------------
REM Wrapper the Windows Task Scheduler job runs once per day ("evergreen").
REM Runs a full incremental ingestion pass across ALL open-data jurisdictions:
REM discovers new permits, detects modified permits (writing a new immutable
REM PermitVersion), and never overwrites data. Uses a rolling 60-day window
REM (Socrata/ArcGIS filter server-side on their incremental date field; other
REM sources re-scan and rely on idempotent upserts) so the daily run stays
REM bounded and polite to the free public APIs. Geocoding + enrichment + scoring
REM are ON so newly-discovered permits get the full treatment.
REM
REM Appends a timestamped log to backend\logs\daily_ingest.log.
REM Registered via schtasks as ConstructionIntel-Daily-Ingest -- see README.
REM ---------------------------------------------------------------------------
set BACKEND_DIR=C:\Users\schar\construction-intel\backend
cd /d "%BACKEND_DIR%"
if not exist "%BACKEND_DIR%\logs" mkdir "%BACKEND_DIR%\logs"
echo ===== Daily ingest run: %DATE% %TIME% ===== >> "%BACKEND_DIR%\logs\daily_ingest.log"
"%BACKEND_DIR%\venv\Scripts\python.exe" "%BACKEND_DIR%\scripts\run_ingest.py" --all --since-days 60 --limit 0 >> "%BACKEND_DIR%\logs\daily_ingest.log" 2>&1
echo ===== exit code %ERRORLEVEL% ===== >> "%BACKEND_DIR%\logs\daily_ingest.log"
