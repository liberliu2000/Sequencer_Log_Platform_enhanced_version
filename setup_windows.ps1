$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host ("=" * 58)
    Write-Host $Message
    Write-Host ("=" * 58)
}

function Get-PythonCommand {
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @("python")
    }

    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @("py", "-3")
    }

    throw "Python was not found. Please install Python 3 and make sure it is available in PATH."
}

function Invoke-ExternalCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$CommandParts
    )

    Write-Host ("> " + ($CommandParts -join " "))
    & $CommandParts[0] @CommandParts[1..($CommandParts.Length - 1)]
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE: $($CommandParts -join ' ')"
    }
}

$ProjectRoot = (Resolve-Path $PSScriptRoot).Path
Set-Location $ProjectRoot

Write-Host "CycleDash Windows setup"
Write-Host "Project root: $ProjectRoot"

$PythonCmd = Get-PythonCommand
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$VenvActivate = Join-Path $ProjectRoot ".venv\Scripts\Activate.ps1"

try {
    Write-Step "[1/6] Create virtual environment"
    if (Test-Path $VenvPython) {
        Write-Host ".venv already exists, skipping venv creation."
    } else {
        Invoke-ExternalCommand -CommandParts ($PythonCmd + @("-m", "venv", ".venv"))
    }

    Write-Step "[2/6] Activate virtual environment"
    if (-not (Test-Path $VenvActivate)) {
        throw "Virtual environment activation script was not found: $VenvActivate"
    }
    . $VenvActivate
    if (-not $env:VIRTUAL_ENV) {
        throw "Virtual environment activation did not complete successfully."
    }
    Write-Host "Activated virtual environment: $env:VIRTUAL_ENV"

    Write-Step "[3/6] Upgrade pip"
    Invoke-ExternalCommand -CommandParts @($VenvPython, "-m", "pip", "install", "--upgrade", "pip")

    Write-Step "[4/6] Install requirements"
    $RequirementsFile = Join-Path $ProjectRoot "requirements.txt"
    if (-not (Test-Path $RequirementsFile)) {
        throw "requirements.txt was not found."
    }
    Invoke-ExternalCommand -CommandParts @($VenvPython, "-m", "pip", "install", "-r", $RequirementsFile)

    Write-Step "[5/6] Prepare .env"
    $EnvExample = Join-Path $ProjectRoot ".env.example"
    $EnvFile = Join-Path $ProjectRoot ".env"
    if (-not (Test-Path $EnvExample)) {
        throw ".env.example was not found."
    }
    if (Test-Path $EnvFile) {
        Write-Host ".env already exists, keeping the current file."
    } else {
        Copy-Item $EnvExample $EnvFile -Force
        Write-Host "Created .env from .env.example"
    }

    Write-Step "[6/6] Initialize database"
    Invoke-ExternalCommand -CommandParts @($VenvPython, "-m", "scripts.init_db")

    Write-Host ""
    Write-Host "Setup completed successfully."
    exit 0
}
catch {
    Write-Host ""
    Write-Host "Setup failed." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
