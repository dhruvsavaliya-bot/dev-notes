@echo off
rem ---- dev-notes automatic runner (used by Task Scheduler) ----
cd /d E:\dev-notes\dev-notes
python add-note.py >> .content\auto-log.txt 2>&1
