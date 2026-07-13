@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "VENV_DIR=%~dp0env"
set "PYTHON=%VENV_DIR%\Scripts\python.exe"
set "STEP_RUNNER=%~dp0scripts\launch_step.py"
set "PADDLE_PATH=%VENV_DIR%\Lib\site-packages\torch\lib"
set "PATH=%PADDLE_PATH%;%VENV_DIR%\Scripts;PortableGit\cmd;%PATH%"
set "ERROR_REPORTING=FALSE"
set "PYTHONUNBUFFERED=1"
set "PIP_PROGRESS_BAR=on"
set "BALLOONTRANS_UPDATE_REPO=https://github.com/CoSciBlog/BallonsTranslator-vibe.git"
set "BALLOONTRANS_UPDATE_BRANCH=dev"

mkdir tmp 2>NUL
type NUL >tmp\stdout.txt
type NUL >tmp\stderr.txt

echo.
echo BallonsTranslator Vibe launcher with auto-update
echo Working directory: "%CD%"
echo Virtual environment: "%VENV_DIR%"
echo.

if exist "%PYTHON%" goto :check_pip

python "%STEP_RUNNER%" "Creating Python virtual environment in %VENV_DIR%" -- python -m venv "%VENV_DIR%"
if %ERRORLEVEL% == 0 goto :install_requirements
echo Couldn't create Python virtual environment
goto :show_stdout_stderr

:check_pip
echo Checking pip in virtual environment...
"%PYTHON%" -m pip --help >NUL 2>tmp\stderr.txt
if %ERRORLEVEL% == 0 goto :launch
echo Couldn't launch pip from virtual environment
goto :show_stdout_stderr

:install_requirements
"%PYTHON%" "%STEP_RUNNER%" "Installing/upgrading pip, wheel, and compatible setuptools" -- "%PYTHON%" -m pip install --upgrade pip wheel setuptools==71.1.0 --progress-bar on
if not %ERRORLEVEL% == 0 goto :show_stdout_stderr
"%PYTHON%" "%STEP_RUNNER%" "Installing BallonsTranslator requirements from requirements.txt" -- "%PYTHON%" -m pip install -r requirements.txt --progress-bar on
if not %ERRORLEVEL% == 0 goto :show_stdout_stderr
goto :launch

:launch
echo Starting BallonsTranslator Vibe with update check...
"%PYTHON%" -u launch.py --update %*
pause
exit /b

:show_stdout_stderr
echo.
echo exit code: %errorlevel%

for %%i in (tmp\stdout.txt) do set size=%%~zi
if "%size%"=="0" goto :show_stderr
echo.
echo stdout:
type tmp\stdout.txt

:show_stderr
for %%i in (tmp\stderr.txt) do set size=%%~zi
if "%size%"=="0" goto :endofscript
echo.
echo stderr:
type tmp\stderr.txt

:endofscript
echo.
echo Launch unsuccessful. Exiting.
pause
