@echo off
rem Provided environment setup for Windows. Run beside ImageDescriptionServer.py and the requirements.
rem Students do not need to read or modify this file.
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
echo Online Image Description System - environment setup>setup.log

rem Keep tools, Python and packages inside this assignment folder.
for /f "tokens=1 delims==" %%E in ('set UV_ 2^>nul') do set "%%E="
set "PYTHONHOME="
set "PYTHONPATH="
set "VIRTUAL_ENV="
set "CONDA_PREFIX="
set "CARGO_DIST_FORCE_INSTALL_DIR="
set "UV_VERSION=0.10.9"
set "PYTHON_VERSION=3.11.15"
set "UV_EXE=%CD%\.tools\uv\uv.exe"
set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
set "UV_UNMANAGED_INSTALL=%CD%\.tools\uv"
set "UV_PYTHON_INSTALL_DIR=%CD%\.runtime\python"
set "UV_CACHE_DIR=%CD%\.runtime\uv-cache"
set "UV_NO_CONFIG=true"
set "UV_MANAGED_PYTHON=true"
set "UV_NATIVE_TLS=true"
if not exist ImageDescriptionServer.py goto missing
if not exist requirements.lock.txt goto missing

echo [1/4] Preparing uv %UV_VERSION%...
if not exist "%UV_EXE%" (
    powershell.exe -NoLogo -NoProfile -Command "$ErrorActionPreference='Stop'; irm 'https://astral.sh/uv/%UV_VERSION%/install.ps1' | iex" >>setup.log 2>&1
    if errorlevel 1 goto failed
)
"%UV_EXE%" --version >>setup.log 2>&1
if errorlevel 1 goto failed
findstr /b /c:"uv %UV_VERSION% " setup.log >nul
if errorlevel 1 goto incompatible

echo [2/4] Preparing Python %PYTHON_VERSION% and .venv...
rem Reuse a matching environment; never delete or rebuild an existing one.
if exist .venv (
    if not exist .venv\pyvenv.cfg goto incompatible
    "%PYTHON_EXE%" --version >>setup.log 2>&1
    if errorlevel 1 goto incompatible
    findstr /x /c:"Python %PYTHON_VERSION%" setup.log >nul
    if errorlevel 1 goto incompatible
)
"%UV_EXE%" python install --managed-python --no-bin --no-registry cpython-%PYTHON_VERSION%-windows-x86_64-none >>setup.log 2>&1
if errorlevel 1 goto failed
if not exist .venv (
    "%UV_EXE%" venv --managed-python --python cpython-%PYTHON_VERSION%-windows-x86_64-none .venv >>setup.log 2>&1
    if errorlevel 1 goto failed
)

echo [3/4] Installing the pinned CPU dependencies. Downloads may take a few minutes...
"%UV_EXE%" pip install --python "%PYTHON_EXE%" --only-binary :all: --reinstall-package torch --torch-backend cpu -r requirements.lock.txt >>setup.log 2>&1
if errorlevel 1 goto failed

echo [4/4] Checking dependencies...
"%UV_EXE%" pip check --python "%PYTHON_EXE%" >>setup.log 2>&1
if errorlevel 1 goto failed
echo Setup complete. Use .venv\Scripts\python.exe; activation is not needed.
echo Check the AI with: .\.venv\Scripts\python.exe ImageDescriptionServer.py --check-ai .\test_images\cat.jpg
echo Log: %CD%\setup.log
pause
exit /b 0

:incompatible
echo The existing uv or .venv version is incompatible. Contact the TA; it was left unchanged.
goto failed
:missing
echo ImageDescriptionServer.py or requirements.lock.txt is missing. Extract the complete assignment ZIP first.
:failed
echo Setup failed. The available installation output follows:
type setup.log
echo Send setup.log to the TA if retrying does not help.
pause
exit /b 1
