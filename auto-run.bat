@echo off
rem ---- dev-notes automatic runner (used by Task Scheduler) ----
cd /d E:\dev-notes\dev-notes

rem The log is gitignored, so nothing else ever prunes it. Past ~1 MB, keep one
rem previous generation and start a fresh file.
if exist .content\auto-log.txt for %%F in (.content\auto-log.txt) do if %%~zF GTR 1048576 move /y .content\auto-log.txt .content\auto-log.1.txt >nul

rem Stamp every run. Un-stamped output is why a failure in this log can only be
rem dated by guessing from its contents -- which is exactly what the last
rem wedge cost: days of failed runs that all looked alike.
echo.>> .content\auto-log.txt
echo ---- run %DATE% %TIME% ---->> .content\auto-log.txt
python add-note.py >> .content\auto-log.txt 2>&1
echo ---- exit %ERRORLEVEL% ---->> .content\auto-log.txt
