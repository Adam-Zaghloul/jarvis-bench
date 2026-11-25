@echo off
rem JARVIS bench assistant: starts the local server (127.0.0.1 only) and opens the browser.
rem Close this window or press Ctrl+C to stop JARVIS.
rem   jarvis.bat backup [--dest FOLDER]   back up bench data    jarvis.bat eval   run the golden set
setlocal
cd /d "%~dp0"
title JARVIS
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python 3 not found. Install it from python.org ^(tick "Add to PATH"^), then run jarvis.bat again.
  pause
  exit /b 1
)
if /i "%~1"=="backup" (
  %PY% jarvis\backup.py %2 %3 %4
  pause
  exit /b
)
if /i "%~1"=="eval" (
  %PY% jarvis\eval.py
  pause
  exit /b
)
where claude >nul 2>nul || echo WARNING: claude not found on PATH. JARVIS will start, but Ask / Seen before / Debrief need Claude Code.
%PY% jarvis\server.py --open %*
if errorlevel 1 pause
