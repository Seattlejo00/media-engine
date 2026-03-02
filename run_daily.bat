@echo off
REM ── The AI Daily — scheduled daily run ──
REM Optimal YouTube posting: 8 AM Pacific → published ~8:15 AM PT / 11:15 AM ET

cd /d "C:\Users\seatt\Desktop\python_work\media-engine"

REM Timestamp for log file
for /f "tokens=1-3 delims=/ " %%a in ('date /t') do set DATESTAMP=%%c-%%a-%%b
set LOGFILE=output\run_%DATESTAMP%.log

echo ============================================ >> "%LOGFILE%" 2>&1
echo Run started: %date% %time% >> "%LOGFILE%" 2>&1
echo ============================================ >> "%LOGFILE%" 2>&1

REM Run the pipeline
"C:\Users\seatt\AppData\Local\Programs\Python\Python312\python.exe" main.py >> "%LOGFILE%" 2>&1

echo ============================================ >> "%LOGFILE%" 2>&1
echo Run finished: %date% %time% >> "%LOGFILE%" 2>&1
echo Exit code: %ERRORLEVEL% >> "%LOGFILE%" 2>&1
echo ============================================ >> "%LOGFILE%" 2>&1
