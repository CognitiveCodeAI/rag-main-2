<#
.SYNOPSIS
    NPR RAG - First-time setup script for Windows.

.DESCRIPTION
    Bootstraps the entire development environment:
      1. Checks prerequisites (Docker, Python, Node, npm)
      2. Starts infrastructure via docker compose
      3. Copies .env.example to .env, prompts for OPENAI_API_KEY
      4. Creates Python venv and installs dependencies
      5. Runs database/collection/bucket setup (setup_all.py)
      6. Installs frontend Node dependencies
      7. Verifies all service connections
      8. Prints summary and next steps

    Every step is idempotent - safe to re-run.

.PARAMETER SkipDocker
    Skip docker compose up (use if infrastructure is already running or remote).

.PARAMETER OpenAIKey
    Pass the OpenAI API key non-interactively (useful for CI).

.EXAMPLE
    .\setup.ps1
    .\setup.ps1 -SkipDocker
    .\setup.ps1 -OpenAIKey "sk-..."
#>

param(
    [switch]$SkipDocker,
    [string]$OpenAIKey
)

$ErrorActionPreference = "Stop"

# -- Paths -----------------------------------------------------------------
$RootDir      = $PSScriptRoot
$BackendDir   = Join-Path $RootDir "backend"
$FrontendDir  = Join-Path $RootDir "frontend"
$EnvExample   = Join-Path $BackendDir ".env.example"
$EnvFile      = Join-Path $BackendDir ".env"
$VenvDir      = Join-Path $BackendDir "venv"
$VenvPython   = Join-Path $VenvDir "Scripts\python.exe"
$Requirements = Join-Path $BackendDir "requirements.txt"
$NodeModules  = Join-Path $FrontendDir "node_modules"

# -- Helpers ----------------------------------------------------------------

function Write-Step  { param([int]$N, [string]$Msg) Write-Host "`n[$N/8] $Msg" -ForegroundColor Cyan }
function Write-Ok    { param([string]$Msg) Write-Host "  [OK] $Msg" -ForegroundColor Green }
function Write-Warn  { param([string]$Msg) Write-Host "  [WARN] $Msg" -ForegroundColor Yellow }
function Write-Err   { param([string]$Msg) Write-Host "  [ERROR] $Msg" -ForegroundColor Red }
function Write-Info  { param([string]$Msg) Write-Host "  $Msg" -ForegroundColor Gray }

function Get-DockerCompose {
    # Prefer "docker compose" (v2), fall back to "docker-compose" (v1)
    try {
        $null = & docker compose version 2>$null
        if ($LASTEXITCODE -eq 0) { return "docker compose" }
    } catch {}
    try {
        $null = & docker-compose version 2>$null
        if ($LASTEXITCODE -eq 0) { return "docker-compose" }
    } catch {}
    return $null
}

function Get-PythonCmd {
    # Prefer "python", fall back to "py -3" (Windows Python Launcher)
    try {
        $v = & python --version 2>&1
        if ($LASTEXITCODE -eq 0 -and "$v" -match "Python 3") { return "python" }
    } catch {}
    try {
        $v = & py -3 --version 2>&1
        if ($LASTEXITCODE -eq 0) { return "py" }
    } catch {}
    return $null
}

function Test-MinVersion {
    param([string]$Actual, [int]$MajorMin, [int]$MinorMin)
    if ($Actual -match "(\d+)\.(\d+)") {
        $maj = [int]$Matches[1]; $min = [int]$Matches[2]
        return ($maj -gt $MajorMin) -or ($maj -eq $MajorMin -and $min -ge $MinorMin)
    }
    return $false
}

# -- Banner -----------------------------------------------------------------

Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  NPR - Near-Perfect RAG  |  First-Time Setup" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

# ==========================================================================
# Step 1: Check prerequisites
# ==========================================================================
Write-Step 1 "Checking prerequisites"

$errors = @()

# Docker
if (-not $SkipDocker) {
    $dc = Get-DockerCompose
    if (-not $dc) {
        $errors += "Docker not found. Install Docker Desktop: https://www.docker.com/products/docker-desktop/"
    } else {
        Write-Ok "Docker Compose: $dc"
    }
} else {
    Write-Info "Docker check skipped (-SkipDocker)"
}

# Python
$pythonCmd = Get-PythonCmd
if (-not $pythonCmd) {
    $errors += "Python 3.10+ not found. Install from https://www.python.org/downloads/"
} else {
    if ($pythonCmd -eq "python") {
        $pyVer = & python --version 2>&1
    } else {
        $pyVer = & py -3 --version 2>&1
    }
    $pyVerStr = "$pyVer" -replace "Python\s*", ""
    if (-not (Test-MinVersion $pyVerStr 3 10)) {
        $errors += "Python 3.10+ required, found $pyVerStr"
    } else {
        Write-Ok "Python: $pyVerStr (command: $pythonCmd)"
    }
}

# Node.js
try {
    $nodeVer = & node --version 2>&1
    $nodeVerStr = "$nodeVer" -replace "v", ""
    if (-not (Test-MinVersion $nodeVerStr 18 0)) {
        $errors += "Node.js 18+ required, found $nodeVerStr. Install from https://nodejs.org/"
    } else {
        Write-Ok "Node.js: $nodeVerStr"
    }
} catch {
    $errors += "Node.js not found. Install from https://nodejs.org/"
}

# npm
try {
    $npmVer = & npm --version 2>&1
    Write-Ok "npm: $npmVer"
} catch {
    $errors += "npm not found. It should come with Node.js - reinstall Node."
}

if ($errors.Count -gt 0) {
    Write-Host ""
    foreach ($e in $errors) { Write-Err $e }
    Write-Host ""
    Write-Host "Fix the above issues and re-run .\setup.ps1" -ForegroundColor Red
    exit 1
}

# ==========================================================================
# Step 2: Start infrastructure
# ==========================================================================
Write-Step 2 "Starting infrastructure (Docker)"

if ($SkipDocker) {
    Write-Info "Skipped (-SkipDocker flag)"
} else {
    $dc = Get-DockerCompose

    Write-Info "Running: $dc up -d"
    if ($dc -eq "docker compose") {
        & docker compose -f (Join-Path $RootDir "docker-compose.yml") up -d
    } else {
        & docker-compose -f (Join-Path $RootDir "docker-compose.yml") up -d
    }

    if ($LASTEXITCODE -ne 0) {
        Write-Err "docker compose up failed. Is Docker Desktop running?"
        exit 1
    }

    # Poll container health
    $containers = @("rag-postgres", "rag-milvus", "rag-minio", "rag-redis")
    $timeout = 180
    $interval = 5

    Write-Info "Waiting for containers to become healthy (timeout: ${timeout}s)..."

    foreach ($ctr in $containers) {
        $healthy = $false
        $startTime = Get-Date
        while (-not $healthy) {
            $elapsed = ((Get-Date) - $startTime).TotalSeconds
            if ($elapsed -ge $timeout) { break }
            try {
                $status = (& docker inspect --format '{{.State.Health.Status}}' $ctr 2>&1).Trim()
                if ($status -eq "healthy") {
                    $healthy = $true
                    Write-Ok "$ctr is healthy"
                    break
                }
            } catch {}
            Start-Sleep -Seconds $interval
        }
        if (-not $healthy) {
            Write-Warn "$ctr did not become healthy within ${timeout}s (may still be starting)"
        }
    }
}

# ==========================================================================
# Step 3: Configure environment (.env)
# ==========================================================================
Write-Step 3 "Configuring environment"

if (Test-Path $EnvFile) {
    Write-Ok ".env already exists - skipping copy"
} else {
    if (-not (Test-Path $EnvExample)) {
        Write-Err ".env.example not found at $EnvExample"
        exit 1
    }
    Copy-Item $EnvExample $EnvFile
    Write-Ok "Copied .env.example -> .env"
}

# Check / set OPENAI_API_KEY
$envContent = Get-Content $EnvFile -Raw
$placeholder = "your-openai-api-key-here"

if ($envContent -match "OPENAI_API_KEY\s*=\s*$placeholder") {
    if ($OpenAIKey) {
        $envContent = $envContent -replace "OPENAI_API_KEY\s*=\s*.*", "OPENAI_API_KEY=$OpenAIKey"
        Set-Content -Path $EnvFile -Value $envContent -NoNewline
        Write-Ok "Set OPENAI_API_KEY from -OpenAIKey parameter"
    } else {
        Write-Warn "OPENAI_API_KEY is still the placeholder value."
        $key = Read-Host "  Enter your OpenAI API key (or press Enter to skip)"
        if ($key) {
            $envContent = $envContent -replace "OPENAI_API_KEY\s*=\s*.*", "OPENAI_API_KEY=$key"
            Set-Content -Path $EnvFile -Value $envContent -NoNewline
            Write-Ok "OPENAI_API_KEY updated"
        } else {
            Write-Warn "Skipped. Edit backend/.env before embeddings will work."
        }
    }
} else {
    Write-Ok "OPENAI_API_KEY is already configured"
}

# ==========================================================================
# Step 4: Python virtual environment
# ==========================================================================
Write-Step 4 "Setting up Python virtual environment"

if (Test-Path $VenvPython) {
    Write-Ok "venv already exists at $VenvDir"
} else {
    Write-Info "Creating venv..."
    if ($pythonCmd -eq "python") {
        & python -m venv $VenvDir
    } else {
        & py -3 -m venv $VenvDir
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to create virtual environment"
        exit 1
    }
    Write-Ok "Created venv at $VenvDir"
}

Write-Info "Installing Python dependencies..."
& $VenvPython -m pip install --upgrade pip --quiet 2>&1 | Out-Null
& $VenvPython -m pip install -r $Requirements --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Err "pip install failed. Check the output above."
    exit 1
}
Write-Ok "Python dependencies installed"

# ==========================================================================
# Step 5: Database / collection / bucket setup
# ==========================================================================
Write-Step 5 "Running database setup (migrations, collections, buckets)"

Push-Location $BackendDir
try {
    & $VenvPython -m scripts.setup.setup_all 2>&1 | ForEach-Object {
        $line = $_
        if ($line -match "\[ERROR\]|\[FAILED\]") { Write-Host "  $line" -ForegroundColor Red }
        elseif ($line -match "\[OK\]|\[SUCCESS\]") { Write-Host "  $line" -ForegroundColor Green }
        else { Write-Host "  $line" -ForegroundColor Gray }
    }
} finally {
    Pop-Location
}

# ==========================================================================
# Step 6: Frontend dependencies
# ==========================================================================
Write-Step 6 "Installing frontend dependencies"

if (Test-Path $NodeModules) {
    Write-Ok "node_modules already exists - skipping npm install"
} else {
    Write-Info "Running npm install in frontend/..."
    Push-Location $FrontendDir
    try {
        & npm install
        if ($LASTEXITCODE -ne 0) {
            Write-Err "npm install failed"
            exit 1
        }
        Write-Ok "Frontend dependencies installed"
    } finally {
        Pop-Location
    }
}

# ==========================================================================
# Step 7: Verify connections
# ==========================================================================
Write-Step 7 "Verifying service connections"

Push-Location $BackendDir
try {
    & $VenvPython -m scripts.setup.verify_connections 2>&1 | ForEach-Object {
        $line = $_
        if ($line -match "\[ERROR\]|\[FAILED\]") { Write-Host "  $line" -ForegroundColor Red }
        elseif ($line -match "\[OK\]|\[SUCCESS\]") { Write-Host "  $line" -ForegroundColor Green }
        else { Write-Host "  $line" -ForegroundColor Gray }
    }
} finally {
    Pop-Location
}

# ==========================================================================
# Step 8: Summary
# ==========================================================================
Write-Step 8 "Setup complete!"

Write-Host ""
Write-Host "========================================================" -ForegroundColor Green
Write-Host "  Setup finished. Next steps:" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  1. Start the application:" -ForegroundColor White
Write-Host "       python run.py" -ForegroundColor Yellow
Write-Host ""
Write-Host "  2. Open in your browser:" -ForegroundColor White
Write-Host "       http://localhost:3000          (App UI)" -ForegroundColor Yellow
Write-Host "       http://localhost:8000/docs     (API docs)" -ForegroundColor Yellow
Write-Host ""
Write-Host "  3. Upload a document and start chatting!" -ForegroundColor White
Write-Host ""
Write-Host "  Press Ctrl+C in the run.py terminal to stop all services." -ForegroundColor Gray
Write-Host ""
