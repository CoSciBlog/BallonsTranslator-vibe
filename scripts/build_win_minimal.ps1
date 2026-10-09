param (
    [string]$PythonVersion = "3.12.10",
    [string]$Tag = "",
    [switch]$UseLocalSource = $false
)

$ErrorActionPreference = "Stop"

# Define directories and names
$BuildDir = Join-Path $PSScriptRoot "..\build_temp"
$DestName = "Ballonstranslator_win_minium"
$DestDir = Join-Path $BuildDir $DestName
$ZipFile = Join-Path $PSScriptRoot "..\$DestName.zip"

Write-Host "=== Starting BallonsTranslator Minimal Build ==="
Write-Host "Python version: $PythonVersion"
if ($Tag) { Write-Host "Build Tag: $Tag" }
Write-Host "Destination: $DestDir"

# Clean up previous build directories and zip
if (Test-Path $BuildDir) {
    Write-Host "Cleaning up existing build directory..."
    Remove-Item -Recurse -Force $BuildDir
}
if (Test-Path $ZipFile) {
    Write-Host "Cleaning up existing zip file..."
    Remove-Item -Force $ZipFile
}

# Create build directory structure
New-Item -ItemType Directory -Force -Path $DestDir | Out-Null

# Step 1: Get Source Code
if ($UseLocalSource) {
    Write-Host "Using local workspace source..."
    $RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
    
    # Copy project files excluding git, github, temp, and current build dirs
    $ExcludePatterns = @(
        ".git", ".github", ".runtime", ".venv", "build_temp", "*.zip",
        ".idea", ".vscode", "__pycache__"
    )
    
    # Simple copy filter
    Get-ChildItem -Path $RepoRoot -Force | Where-Object {
        $name = $_.Name
        $match = $false
        foreach ($pattern in $ExcludePatterns) {
            if ($name -like $pattern) { $match = $true; break }
        }
        -not $match
    } | Copy-Item -Destination $DestDir -Recurse -Force
} else {
    # Determine download URL
    $SourceUrl = "https://github.com/CoSciBlog/BallonsTranslator-vibe/archive/refs/heads/1.5-vibe.zip"
    if ($Tag) {
        $SourceUrl = "https://github.com/CoSciBlog/BallonsTranslator-vibe/archive/refs/tags/$Tag.zip"
    }
    
    Write-Host "Downloading source code from $SourceUrl ..."
    $SourceZip = Join-Path $BuildDir "source.zip"
    Invoke-WebRequest -Uri $SourceUrl -OutFile $SourceZip
    
    Write-Host "Extracting source code..."
    $ExtractTemp = Join-Path $BuildDir "extract_temp"
    Expand-Archive -Path $SourceZip -DestinationPath $ExtractTemp
    
    # Find the extracted root folder (usually BallonsTranslator-dev or BallonsTranslator-tag)
    $ExtractedFolder = Get-ChildItem -Path $ExtractTemp -Directory | Select-Object -First 1
    if (-not $ExtractedFolder) {
        throw "Could not find extracted folder in source zip"
    }
    
    Write-Host "Moving source files to target destination..."
    Get-ChildItem -LiteralPath $ExtractedFolder.FullName -Force |
        Move-Item -Destination $DestDir -Force
    Remove-Item -Recurse -Force $ExtractTemp
    Remove-Item $SourceZip
}

# Step 2: Build a relocatable uv-managed Python virtual environment.
$VersionFile = Join-Path $DestDir ".python-version"
Set-Content -LiteralPath $VersionFile -Value $PythonVersion -Encoding ascii
$BootstrapScript = Join-Path $DestDir "scripts\bootstrap_windows.ps1"
if (-not (Test-Path $BootstrapScript -PathType Leaf)) {
    throw "Could not find runtime bootstrap in build source: $BootstrapScript"
}

Write-Host "Creating relocatable uv runtime with Python $PythonVersion..."
& $BootstrapScript -ProjectRoot $DestDir -Relocatable
if ($LASTEXITCODE -ne 0) {
    throw "Runtime bootstrap failed with exit code $LASTEXITCODE"
}

$RuntimeCache = Join-Path $DestDir ".runtime\cache"
if (Test-Path $RuntimeCache) {
    Remove-Item -LiteralPath $RuntimeCache -Recurse -Force
}

# Step 3: Create Final Zip Archive
Write-Host "Creating final zip package: $ZipFile ..."
# Compress-Archive stores Windows separators, so write portable entry names explicitly.
Add-Type -AssemblyName System.IO.Compression.FileSystem
$ArchiveRoot = (Resolve-Path $DestDir).Path
$Archive = [System.IO.Compression.ZipFile]::Open(
    $ZipFile,
    [System.IO.Compression.ZipArchiveMode]::Create
)
try {
    Get-ChildItem -LiteralPath $ArchiveRoot -File -Recurse -Force |
        Where-Object { $_.FullName -notmatch '[\\/]__pycache__[\\/]' } |
        ForEach-Object {
            $RelativePath = $_.FullName.Substring($ArchiveRoot.Length + 1).Replace('\', '/')
            $EntryName = "$DestName/$RelativePath"
            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $Archive,
                $_.FullName,
                $EntryName,
                [System.IO.Compression.CompressionLevel]::Optimal
            ) | Out-Null
        }
} finally {
    $Archive.Dispose()
}

# Clean up build temp directory
Write-Host "Cleaning up temporary build folder..."
Remove-Item -Recurse -Force $BuildDir

Write-Host "=== Build Completed Successfully! ==="
Write-Host "Output: $ZipFile"
