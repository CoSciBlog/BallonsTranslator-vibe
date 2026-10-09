@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "RUNTIME_DIR=%~dp0ballontrans_pylibs_win"
set "PYTHON=%RUNTIME_DIR%\python.exe"
set "ERROR_REPORTING=FALSE"

if exist "%~dp0python\" (
    if not exist "%RUNTIME_DIR%\" ren "%~dp0python" "ballontrans_pylibs_win"
)

if exist "%PYTHON%" goto :validate_runtime
if exist "%RUNTIME_DIR%\" goto :incomplete_runtime

echo No local BallonsTranslator Python runtime was found.
echo Installing the supported project-local Python 3.12 runtime...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1"
set "INSTALL_EXIT=%ERRORLEVEL%"
if not "%INSTALL_EXIT%"=="0" (
    echo.
    echo Runtime installation failed with exit code %INSTALL_EXIT%.
    pause
    exit /b %INSTALL_EXIT%
)

rem install.ps1 launches BallonsTranslator after a successful first-time setup.
exit /b 0

:validate_runtime
"%PYTHON%" -c "import sys; raise SystemExit(sys.version_info[:2] not in ((3, 8), (3, 9), (3, 10), (3, 11), (3, 12)))" >NUL 2>&1
if errorlevel 1 goto :unsupported_runtime

set "PATH=%RUNTIME_DIR%;%RUNTIME_DIR%\Scripts;%PATH%"

mkdir tmp 2>NUL
type NUL >"tmp\stdout.txt"
type NUL >"tmp\stderr.txt"

"%PYTHON%" -m pip --help >"tmp\stdout.txt" 2>"tmp\stderr.txt"
if not errorlevel 1 goto :launch
if not defined PIP_INSTALLER_LOCATION goto :pip_failed

"%PYTHON%" "%PIP_INSTALLER_LOCATION%" >"tmp\stdout.txt" 2>"tmp\stderr.txt"
if errorlevel 1 goto :pip_failed

:launch
"%PYTHON%" -m ballontranslator %*
set "APP_EXIT=%ERRORLEVEL%"
if not "%APP_EXIT%"=="0" echo BallonsTranslator exited with code %APP_EXIT%.
pause
exit /b %APP_EXIT%

:incomplete_runtime
echo The local runtime directory exists but does not contain python.exe:
echo   "%RUNTIME_DIR%"
echo Rename or repair that directory, then run scripts\install.bat.
pause
exit /b 1

:unsupported_runtime
echo The local runtime at "%PYTHON%" is not usable or has an unsupported Python version.
echo BallonsTranslator 1.5 requires Python 3.8 through 3.12.
echo Repair the local runtime with scripts\install.bat.
pause
exit /b 1

:pip_failed
set "PIP_EXIT=%ERRORLEVEL%"
echo Couldn't launch or install pip in the local runtime.
echo.
if exist "tmp\stdout.txt" for %%I in ("tmp\stdout.txt") do if %%~zI GTR 0 (
    echo stdout:
    type "tmp\stdout.txt"
    echo.
)
if exist "tmp\stderr.txt" for %%I in ("tmp\stderr.txt") do if %%~zI GTR 0 (
    echo stderr:
    type "tmp\stderr.txt"
    echo.
)
echo Launch unsuccessful. Exiting.
pause
exit /b %PIP_EXIT%
