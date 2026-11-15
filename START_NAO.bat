@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0START_NAO.ps1"
set "EXITCODE=%ERRORLEVEL%"
echo.
if not "%EXITCODE%"=="0" echo NAO startup ended with error code %EXITCODE%.
echo Press any key to close.
pause >nul
exit /b %EXITCODE%
