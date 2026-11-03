@echo off
rem Opens OpenCode in this job-search folder. The OpenRouter key comes from Windows Credential Manager.
cd /d "%~dp0"
title Job search (OpenCode)
call "%~dp0engine\py.cmd" engine\opencode_app.py launch
if errorlevel 1 pause
