@echo off
rem Double-click to add a free job-search API key (Adzuna, Jooble or JSearch). Keys go to Windows Credential Manager.
cd /d "%~dp0"
echo Free job-search API keys (all optional). Which one are you adding?
echo   1. Adzuna   2. Jooble   3. JSearch   (anything else: just show what's stored)
set /p FK_CHOICE="Number: "
if "%FK_CHOICE%"=="1" call "%~dp0engine\py.cmd" engine\keys.py set adzuna
if "%FK_CHOICE%"=="2" call "%~dp0engine\py.cmd" engine\keys.py set jooble
if "%FK_CHOICE%"=="3" call "%~dp0engine\py.cmd" engine\keys.py set jsearch
echo.
call "%~dp0engine\py.cmd" engine\keys.py status
echo.
pause
