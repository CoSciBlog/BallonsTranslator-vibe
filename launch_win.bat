@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PROJECT_ROOT=%~dp0"
set "VENV_DIR=%PROJECT_ROOT%.venv"
set "PYTHON=%VENV_DIR%\Scripts\python.exe"
set "UV_ROOT=%PROJECT_ROOT%.runtime\uv"
set "UV_EXE=%UV_ROOT%\uv.exe"
set "UV_PYTHON_INSTALL_DIR=%PROJECT_ROOT%.runtime\python"
set "UV_CACHE_DIR=%PROJECT_ROOT%.runtime\cache"
set "UV_MANAGED_PYTHON=1"
set "UV_PYTHON_DOWNLOADS=automatic"
set "ERROR_REPORTING=FALSE"

if not exist "%PYTHON%" goto :bootstrap_runtime
if not exist "%UV_EXE%" goto :bootstrap_runtime
goto :validate_runtime

:bootstrap_runtime
echo Preparing the project-local uv, Python, and .venv runtime...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_ROOT%scripts\bootstrap_windows.ps1" -ProjectRoot "%PROJECT_ROOT%"
set "BOOTSTRAP_EXIT=%ERRORLEVEL%"
if not "%BOOTSTRAP_EXIT%"=="0" (
    echo.
    echo Runtime setup failed with exit code %BOOTSTRAP_EXIT%.
    pause
    exit /b %BOOTSTRAP_EXIT%
)

if not exist "%PYTHON%" (
    echo Runtime setup completed without creating "%PYTHON%".
    pause
    exit /b 1
)

:validate_runtime
"%PYTHON%" -c "import sys; raise SystemExit(sys.version_info[:3] != (3, 12, 10))" >NUL 2>&1
if errorlevel 1 goto :unsupported_runtime

if not exist "%UV_EXE%" goto :missing_uv

set "VIRTUAL_ENV=%VENV_DIR%"
set "PATH=%VENV_DIR%\Scripts;%UV_ROOT%;%PATH%"

"%PYTHON%" -m ballontranslator %*
set "APP_EXIT=%ERRORLEVEL%"
if not "%APP_EXIT%"=="0" echo BallonsTranslator exited with code %APP_EXIT%.
pause
exit /b %APP_EXIT%

:unsupported_runtime
echo The project virtual environment does not use the pinned Python 3.12.10 runtime:
echo   "%PYTHON%"
echo Existing environments are never deleted automatically.
echo Rename or repair .venv, then run launch_win.bat again.
pause
exit /b 1

:missing_uv
echo The project virtual environment exists, but project-local uv is missing:
echo   "%UV_EXE%"
echo Run scripts\install.bat to repair the project runtime.
pause
exit /b 1
