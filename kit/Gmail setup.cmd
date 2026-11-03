@echo off
rem Double-click to let the kit read your Gmail "Job Alerts" label every morning (read-only).
rem Needs 2-Step Verification on your Google account. The app password is kept in Windows Credential Manager.
cd /d "%~dp0"
call "%~dp0engine\py.cmd" engine\gmail_imap.py setup
echo.
pause
