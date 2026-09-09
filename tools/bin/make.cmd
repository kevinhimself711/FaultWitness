@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%\..\..") do set "REPO_ROOT=%%~fI"

if "%~1"=="" (
  echo Usage: make verify-fast
  exit /b 2
)

if /I not "%~1"=="verify-fast" (
  echo Only verify-fast is an active make target. Historical Gate commands live at their tags.
  exit /b 2
)

pushd "%REPO_ROOT%" >nul
uv run python -m faultwitness_dev %*
set "EXIT_CODE=%ERRORLEVEL%"
popd >nul
exit /b %EXIT_CODE%
