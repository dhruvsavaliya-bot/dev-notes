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

rem Local runs have no GITHUB_TOKEN the way Actions does, so GitHub search is
rem capped at 10 req/min (GH_CALL_BUDGET=8/run) instead of 5000/hr -- trending
rem project sources burn through that in a single sweep. Pick up a token from
rem the gh CLI when one is available so local runs get the same budget;
rem silently stays unset (same as before) if gh isn't installed or logged in.
set GH_TOKEN=
for /f "delims=" %%T in ('gh auth token 2^>nul') do set GH_TOKEN=%%T

python add-note.py >> .content\auto-log.txt 2>&1
echo ---- exit %ERRORLEVEL% ---->> .content\auto-log.txt
