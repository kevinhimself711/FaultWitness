@echo off
setlocal
if not defined FW_SSH_PASSWORD exit /b 2
<nul set /p "=%FW_SSH_PASSWORD%"
