param(
    [string]$ProjectRoot = (Split-Path $PSScriptRoot -Parent),
    [switch]$Relocatable
)

$ErrorActionPreference = "Stop"

$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
$PythonVersionFile = Join-Path $ProjectRoot ".python-version"
$RequirementsFile = Join-Path $ProjectRoot "requirements.txt"
$RuntimeRoot = Join-Path $ProjectRoot ".runtime"
$UvRoot = Join-Path $RuntimeRoot "uv"
$UvExe = Join-Path $UvRoot "uv.exe"
$PythonInstallDir = Join-Path $RuntimeRoot "python"
$UvCacheDir = Join-Path $RuntimeRoot "cache"
$VenvDir = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$UvVersion = "0.12.8"

if (-not (Test-Path $PythonVersionFile -PathType Leaf)) {
    throw "Missing Python version pin: $PythonVersionFile"
}
if (-not (Test-Path $RequirementsFile -PathType Leaf)) {
    throw "Missing requirements file: $RequirementsFile"
}

$PythonVersion = (Get-Content -LiteralPath $PythonVersionFile -Raw).Trim()
if ($PythonVersion -notmatch '^3\.12\.\d+$') {
    throw "Unsupported .python-version value '$PythonVersion'. Expected a pinned Python 3.12 patch release."
}

New-Item -ItemType Directory -Force -Path $RuntimeRoot, $UvRoot, $PythonInstallDir, $UvCacheDir | Out-Null

if (-not (Test-Path $UvExe -PathType Leaf)) {
    $BootstrapDir = Join-Path $RuntimeRoot "bootstrap-$PID"
    $UvArchive = Join-Path $BootstrapDir "uv.zip"
    $UvExtractDir = Join-Path $BootstrapDir "extract"
    $UvUrl = "https://github.com/astral-sh/uv/releases/download/$UvVersion/uv-x86_64-pc-windows-msvc.zip"

    New-Item -ItemType Directory -Force -Path $BootstrapDir, $UvExtractDir | Out-Null
    try {
        Write-Host "Downloading project-local uv $UvVersion..."
        Invoke-WebRequest -Uri $UvUrl -OutFile $UvArchive
        Expand-Archive -LiteralPath $UvArchive -DestinationPath $UvExtractDir -Force
        $DownloadedUv = Get-ChildItem -LiteralPath $UvExtractDir -Filter "uv.exe" -Recurse | Select-Object -First 1
        if (-not $DownloadedUv) {
            throw "The uv archive did not contain uv.exe."
        }
        Copy-Item -LiteralPath $DownloadedUv.FullName -Destination $UvExe -Force
    }
    finally {
        if (Test-Path $BootstrapDir) {
            Remove-Item -LiteralPath $BootstrapDir -Recurse -Force
        }
    }
}

$env:UV_PYTHON_INSTALL_DIR = $PythonInstallDir
$env:UV_CACHE_DIR = $UvCacheDir
$env:UV_MANAGED_PYTHON = "1"
$env:UV_PYTHON_DOWNLOADS = "automatic"

if (Test-Path $VenvDir) {
    if (-not (Test-Path $VenvPython -PathType Leaf)) {
        throw "Existing .venv is incomplete: $VenvPython is missing. Rename or repair .venv before retrying."
    }

    $ExistingVersion = & $VenvPython -c "import platform; print(platform.python_version())"
    if ($LASTEXITCODE -ne 0 -or $ExistingVersion.Trim() -ne $PythonVersion) {
        throw "Existing .venv uses Python $ExistingVersion, but $PythonVersion is required. Rename or repair .venv before retrying."
    }

    Write-Host "Using existing project virtual environment with Python $ExistingVersion."
    return
}

Write-Host "Installing project-local Python $PythonVersion with uv..."
& $UvExe python install $PythonVersion --install-dir $PythonInstallDir --no-bin --no-registry
if ($LASTEXITCODE -ne 0) {
    throw "uv could not install Python $PythonVersion."
}

Write-Host "Creating project virtual environment at $VenvDir..."
$VenvArguments = @('venv', '--python', $PythonVersion, '--managed-python', '--seed')
if ($Relocatable) {
    $VenvArguments += '--relocatable'
}
$VenvArguments += $VenvDir
& $UvExe @VenvArguments
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPython -PathType Leaf)) {
    throw "uv could not create the project virtual environment."
}

Write-Host "Installing core requirements into .venv..."
& $UvExe pip install --python $VenvPython -r $RequirementsFile
if ($LASTEXITCODE -ne 0) {
    throw "uv could not install the core requirements into .venv."
}

Write-Host "Project runtime ready: $VenvPython"
