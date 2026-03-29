$ErrorActionPreference = "Stop"

function Get-PythonCommandParts {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path $VenvPython) {
        return @($VenvPython)
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @("python")
    }

    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @("py", "-3")
    }

    throw "Python was not found. Please install Python 3 or create .venv first."
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

function Invoke-ExternalCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$CommandParts
    )

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

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

$PythonCommandParts = Get-PythonCommandParts -ProjectRoot $ProjectRoot
$PythonExecutable = $PythonCommandParts[0]
$EnvFile = Join-Path $ProjectRoot ".env"
$ApiPort = Get-DotEnvValue -Path $EnvFile -Key "APP_PORT" -DefaultValue "8000"
$ApiDocsUrl = "http://127.0.0.1:${ApiPort}/docs"
$ApiHealthUrl = "http://127.0.0.1:${ApiPort}/api/v1/health"
$StreamlitUrl = "http://127.0.0.1:8501"

Write-Host "[1/3] Install requirements"
Invoke-ExternalCommand -CommandParts ($PythonCommandParts + @("-m", "pip", "install", "-r", "requirements.txt"))

Write-Host "[2/3] Initialize database"
Invoke-ExternalCommand -CommandParts ($PythonCommandParts + @("$ProjectRoot\scripts\init_db.py"))

Write-Host "[3/3] Launch FastAPI and Streamlit"
Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", "& '$PythonExecutable' '$ProjectRoot\scripts\run_api.py'" -WorkingDirectory $ProjectRoot | Out-Null
Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", "& '$PythonExecutable' '$ProjectRoot\scripts\run_ui.py'" -WorkingDirectory $ProjectRoot | Out-Null

Write-Host "Waiting for FastAPI: $ApiHealthUrl"
if (Wait-HttpReady -Url $ApiHealthUrl -TimeoutSeconds 60) {
    Start-Process $ApiDocsUrl | Out-Null
    Write-Host "Opened FastAPI docs: $ApiDocsUrl"
} else {
    Write-Host "FastAPI did not become ready within 60 seconds. Open manually if needed: $ApiDocsUrl" -ForegroundColor Yellow
}

Write-Host "Waiting for Streamlit: $StreamlitUrl"
if (Wait-HttpReady -Url $StreamlitUrl -TimeoutSeconds 90) {
    Start-Process $StreamlitUrl | Out-Null
    Write-Host "Opened Streamlit UI: $StreamlitUrl"
} else {
    Write-Host "Streamlit did not become ready within 90 seconds. Open manually if needed: $StreamlitUrl" -ForegroundColor Yellow
}
