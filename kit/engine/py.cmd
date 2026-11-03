@echo off
rem Runs Python with the given arguments: the py launcher, else python on PATH, else the per-user install setup made.
set "FK_PY="
where py >nul 2>nul && set "FK_PY=py -3"
if not defined FK_PY (where python >nul 2>nul && for /f "delims=" %%p in ('where python') do if not defined FK_PY echo %%p | findstr /i /v "WindowsApps" >nul && set "FK_PY="%%p"")
if not defined FK_PY if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "FK_PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe""
if not defined FK_PY (echo Python isn't installed yet: double-click setup.cmd first. & exit /b 1)
%FK_PY% %*
