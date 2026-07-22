@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%\..\..") do set "REPO_ROOT=%%~fI"

if "%~1"=="" (
  echo Usage: make ^<verify-fast^|eval-changed^|audit-g00^|eval-g00^>
  exit /b 2
)

pushd "%REPO_ROOT%" >nul
uv run python -m faultwitness_dev %*
set "EXIT_CODE=%ERRORLEVEL%"
popd >nul
exit /b %EXIT_CODE%
