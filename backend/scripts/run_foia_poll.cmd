@echo off
REM ---------------------------------------------------------------------------
REM Wrapper the Windows Task Scheduler job runs every 6 hours.
REM Polls Gmail for FOIA replies, parses attachments, ingests permit records.
REM Appends a timestamped log to backend\logs\foia_poll.log.
REM
REM Registered via schtasks -- see backend\README.md ("FOIA email intake").
REM ---------------------------------------------------------------------------
set BACKEND_DIR=C:\Users\schar\construction-intel\backend
cd /d "%BACKEND_DIR%"
if not exist "%BACKEND_DIR%\logs" mkdir "%BACKEND_DIR%\logs"
echo ===== FOIA poll run: %DATE% %TIME% ===== >> "%BACKEND_DIR%\logs\foia_poll.log"
"%BACKEND_DIR%\venv\Scripts\python.exe" "%BACKEND_DIR%\scripts\poll_foia_replies.py" >> "%BACKEND_DIR%\logs\foia_poll.log" 2>&1
echo ===== exit code %ERRORLEVEL% ===== >> "%BACKEND_DIR%\logs\foia_poll.log"
