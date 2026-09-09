@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%\..\..") do set "REPO_ROOT=%%~fI"

if "%~1"=="" (
  echo Usage: make verify-fast or make verify-docs
  exit /b 2
)

if /I not "%~1"=="verify-fast" if /I not "%~1"=="verify-docs" (
  echo Only verify-fast and verify-docs are active make targets. Historical Gate commands live at their tags.
  exit /b 2
)

pushd "%REPO_ROOT%" >nul
uv run python -m faultwitness_dev %*
set "EXIT_CODE=%ERRORLEVEL%"
popd >nul
exit /b %EXIT_CODE%
