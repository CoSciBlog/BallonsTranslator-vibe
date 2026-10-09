param(
    [switch]$NoLaunch
)

$ErrorActionPreference = "Stop"
$AppName = "BallonsTranslator-vibe"
$SourceUrl = "https://github.com/CoSciBlog/BallonsTranslator-vibe/archive/refs/heads/1.5-vibe.zip"

$IsLocal = $false
$ProjectRoot = ""

if ($PSScriptRoot) {
    $ParentDir = Split-Path $PSScriptRoot -Parent
    if (Test-Path (Join-Path $ParentDir "ballontranslator")) {
        $IsLocal = $true
        $ProjectRoot = $ParentDir
    }
}

if (-not $IsLocal) {
    $CurrentDir = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath(".")
    $ProjectRoot = Join-Path $CurrentDir $AppName
    Write-Host "=== BallonsTranslator Vibe Web Installer ==="
    Write-Host "Installing $AppName to $ProjectRoot..."
} else {
    Write-Host "=== BallonsTranslator Vibe Local Installer ==="
    Write-Host "Preparing the project runtime in $ProjectRoot..."
}

$BuildDir = Join-Path $ProjectRoot "install_temp"

if (-not $IsLocal) {
    if (Test-Path $ProjectRoot) {
        $Timestamp = Get-Date -Format "yyyyMMddHHmmss"
        $BackupRoot = "${ProjectRoot}.backup.${Timestamp}"
        Write-Host "Existing folder found. Moving it to $BackupRoot..."
        Rename-Item -LiteralPath $ProjectRoot -NewName (Split-Path $BackupRoot -Leaf)
    }

    New-Item -ItemType Directory -Force -Path $ProjectRoot, $BuildDir | Out-Null
    $SourceZip = Join-Path $BuildDir "source.zip"
    $ExtractTemp = Join-Path $BuildDir "extract_temp"

    Write-Host "Downloading BallonsTranslator Vibe source..."
    Invoke-WebRequest -Uri $SourceUrl -OutFile $SourceZip

    Write-Host "Extracting source..."
    Expand-Archive -LiteralPath $SourceZip -DestinationPath $ExtractTemp
    $ExtractedFolder = Get-ChildItem -LiteralPath $ExtractTemp -Directory | Select-Object -First 1
    if (-not $ExtractedFolder) {
        throw "The downloaded source archive did not contain a project directory."
    }

    Get-ChildItem -LiteralPath $ExtractedFolder.FullName -Force | Move-Item -Destination $ProjectRoot -Force
    Remove-Item -LiteralPath $BuildDir -Recurse -Force
}

$BootstrapScript = Join-Path $ProjectRoot "scripts\bootstrap_windows.ps1"
if (-not (Test-Path $BootstrapScript -PathType Leaf)) {
    throw "Missing Windows runtime bootstrap: $BootstrapScript"
}

& $BootstrapScript -ProjectRoot $ProjectRoot
if ($LASTEXITCODE -ne 0) {
    throw "Project runtime bootstrap failed with exit code $LASTEXITCODE."
}

Write-Host "=== Installation completed successfully ==="
Write-Host "Python and all packages are isolated in $ProjectRoot\.venv."
Write-Host "uv, its managed Python, and its cache are stored in $ProjectRoot\.runtime."

if (-not $NoLaunch) {
    $LaunchBat = Join-Path $ProjectRoot "launch_win.bat"
    if (Test-Path $LaunchBat -PathType Leaf) {
        Write-Host "Launching BallonsTranslator Vibe..."
        Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$LaunchBat`"" -WorkingDirectory $ProjectRoot
    }
}
