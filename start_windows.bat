@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
setlocal

rem One-click launcher for Windows 10/11.
rem bootstrap.py creates .venv, installs missing deps and starts the pet detached.
rem All messages here are ASCII on purpose: .bat files with non-ASCII text can be
rem mangled by the Windows console codepage.

set "BOOT_PY="
where py >nul 2>&1
if not errorlevel 1 set "BOOT_PY=py -3"
if not defined BOOT_PY (
  where python >nul 2>&1
  if not errorlevel 1 set "BOOT_PY=python"
)
if not defined BOOT_PY (
  echo [ERROR] Python 3.9-3.13 not found.
  echo Install from https://www.python.org/downloads/
  echo Remember to check "Add Python to PATH" during setup.
  pause
  exit /b 1
)

%BOOT_PY% bootstrap.py
if errorlevel 1 (
  echo [ERROR] Setup failed. Run this for details:
  echo   %BOOT_PY% bootstrap.py --check
  pause
  exit /b 1
)

endlocal
exit /b 0
