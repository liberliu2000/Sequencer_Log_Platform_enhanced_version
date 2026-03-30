$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host ("=" * 58)
    Write-Host $Message
    Write-Host ("=" * 58)
}

function Get-PythonCommand {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $PreferredVersions = @("3.12", "3.11", "3.10")
        foreach ($Version in $PreferredVersions) {
            & py "-$Version" -c "import sys; print(sys.executable)" *> $null
            if ($LASTEXITCODE -eq 0) {
                return ,@("py", "-$Version")
            }
        }

        return ,@("py", "-3")
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        return ,("python")
    }

    throw "Python was not found. Please install Python 3 and make sure it is available in PATH."
}

function Get-PythonVersionString {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PythonExe
    )

    return (& $PythonExe -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}')").Trim()
}

function Test-SupportedPythonVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string]$VersionString
    )

    try {
        $Version = [Version]$VersionString
        return $Version.Major -eq 3 -and $Version.Minor -ge 10 -and $Version.Minor -le 12
    }
    catch {
        return $false
    }
}

function Invoke-ExternalCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$CommandParts
    )

    Write-Host ("> " + ($CommandParts -join " "))
    $Command = $CommandParts[0]
    $Arguments = @()
    if ($CommandParts.Length -gt 1) {
        $Arguments = $CommandParts[1..($CommandParts.Length - 1)]
    }

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $($CommandParts -join ' ')"
    }
}

function Get-DotEnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Key,
        [string]$DefaultValue = ""
    )

    if (-not (Test-Path $Path)) {
        return $DefaultValue
    }

    foreach ($Line in Get-Content $Path) {
        $Trimmed = $Line.Trim()
        if (-not $Trimmed -or $Trimmed.StartsWith("#")) {
            continue
        }

        if ($Trimmed -like "$Key=*") {
            return $Trimmed.Substring($Key.Length + 1).Trim()
        }
    }

    return $DefaultValue
}

function Wait-HttpReady {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [int]$TimeoutSeconds = 60
    )

    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $Deadline) {
        try {
            $Response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($Response.StatusCode -ge 200 -and $Response.StatusCode -lt 500) {
                return $true
            }
        }
        catch {
            Start-Sleep -Seconds 2
            continue
        }

        Start-Sleep -Seconds 2
    }

    return $false
}

function Start-ServiceWindow {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Title,
        [Parameter(Mandatory = $true)]
        [string]$Command
    )

    Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $Command -WorkingDirectory $ProjectRoot -WindowStyle Normal | Out-Null
    Write-Host "Started $Title window."
}

$ProjectRoot = (Resolve-Path $PSScriptRoot).Path
Set-Location $ProjectRoot

Write-Host "CycleDash Windows setup"
Write-Host "Project root: $ProjectRoot"

$PythonCmd = @(Get-PythonCommand)
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$VenvActivate = Join-Path $ProjectRoot ".venv\Scripts\Activate.ps1"

try {
    Write-Step "[1/7] Create virtual environment"
    if (Test-Path $VenvPython) {
        Write-Host ".venv already exists, skipping venv creation."
        $ExistingVenvVersion = Get-PythonVersionString -PythonExe $VenvPython
        if (-not (Test-SupportedPythonVersion -VersionString $ExistingVenvVersion)) {
            throw ".venv uses Python $ExistingVenvVersion, but this project currently supports Python 3.10-3.12 on Windows. Remove .venv and rerun setup, or recreate it with 'py -3.12 -m venv .venv'."
        }
    } else {
        Invoke-ExternalCommand -CommandParts ($PythonCmd + @("-m", "venv", ".venv"))
        $CreatedVenvVersion = Get-PythonVersionString -PythonExe $VenvPython
        if (-not (Test-SupportedPythonVersion -VersionString $CreatedVenvVersion)) {
            throw "Created .venv with Python $CreatedVenvVersion, but this project currently supports Python 3.10-3.12 on Windows. Recreate it with 'py -3.12 -m venv .venv'."
        }
    }

    Write-Step "[2/7] Activate virtual environment"
    if (-not (Test-Path $VenvActivate)) {
        throw "Virtual environment activation script was not found: $VenvActivate"
    }
    . $VenvActivate
    if (-not $env:VIRTUAL_ENV) {
        throw "Virtual environment activation did not complete successfully."
    }
    Write-Host "Activated virtual environment: $env:VIRTUAL_ENV"

    Write-Step "[3/7] Upgrade pip"
    Invoke-ExternalCommand -CommandParts @($VenvPython, "-m", "pip", "install", "--upgrade", "pip")

    Write-Step "[4/7] Install requirements"
    $RequirementsFile = Join-Path $ProjectRoot "requirements.txt"
    if (-not (Test-Path $RequirementsFile)) {
        throw "requirements.txt was not found."
    }
    Invoke-ExternalCommand -CommandParts @($VenvPython, "-m", "pip", "install", "-r", $RequirementsFile)

    Write-Step "[5/7] Prepare .env"
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

    Write-Step "[6/7] Initialize database"
    Invoke-ExternalCommand -CommandParts @($VenvPython, "-m", "scripts.init_db")

    Write-Step "[7/7] Launch FastAPI and Streamlit"
    $EnvFile = Join-Path $ProjectRoot ".env"
    $ApiPort = Get-DotEnvValue -Path $EnvFile -Key "APP_PORT" -DefaultValue "8000"
    $ApiHost = "127.0.0.1"
    $ApiHealthUrl = "http://${ApiHost}:${ApiPort}/api/v1/health"
    $StreamlitUrl = "http://localhost:8501"

    Start-ServiceWindow -Title "FastAPI" -Command "& '$VenvPython' '$ProjectRoot\scripts\run_api.py'"
    Start-ServiceWindow -Title "Streamlit" -Command "& '$VenvPython' '$ProjectRoot\scripts\run_ui.py'"

    Write-Host "Waiting for FastAPI to become ready: $ApiHealthUrl"
    if (Wait-HttpReady -Url $ApiHealthUrl -TimeoutSeconds 60) {
        Write-Host "FastAPI is ready: $ApiHealthUrl"
    } else {
        Write-Host "FastAPI did not become ready within 60 seconds. API health endpoint: $ApiHealthUrl" -ForegroundColor Yellow
    }

    Write-Host "Waiting for Streamlit to become ready: $StreamlitUrl"
    if (Wait-HttpReady -Url $StreamlitUrl -TimeoutSeconds 90) {
        Start-Process $StreamlitUrl | Out-Null
        Write-Host "Opened Streamlit UI: $StreamlitUrl"
    } else {
        Write-Host "Streamlit did not become ready within 90 seconds. You can open it manually later: $StreamlitUrl" -ForegroundColor Yellow
    }

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
