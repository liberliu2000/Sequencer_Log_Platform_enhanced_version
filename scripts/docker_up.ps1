$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ComposeFile = Join-Path $ProjectRoot "docker-compose.oneclick.yml"
$EnvFile = Join-Path $ProjectRoot ".env.docker"
$EnvExampleFile = Join-Path $ProjectRoot ".env.docker.example"

function Get-EnvValueOrDefault {
    param(
        [hashtable]$Map,
        [string]$Key,
        [string]$DefaultValue
    )

    if ($Map.ContainsKey($Key) -and $Map[$Key]) {
        return [string]$Map[$Key]
    }

    return $DefaultValue
}

$DataDirs = @(
    (Join-Path $ProjectRoot "data"),
    (Join-Path $ProjectRoot "data/uploads"),
    (Join-Path $ProjectRoot "data/exports"),
    (Join-Path $ProjectRoot "data/runtime_logs"),
    (Join-Path $ProjectRoot "data/intermediate_cache"),
    (Join-Path $ProjectRoot "data/tmp")
)

foreach ($Dir in $DataDirs) {
    New-Item -ItemType Directory -Force -Path $Dir | Out-Null
}

if (-not (Test-Path $EnvFile)) {
    Copy-Item $EnvExampleFile $EnvFile
    Write-Host "Created $EnvFile from template. If the service is opened from another machine, update NEXT_PUBLIC_API_BASE_URL first."
}

$EnvVars = @{}
foreach ($Line in Get-Content $EnvFile) {
    $Trimmed = $Line.Trim()
    if (-not $Trimmed -or $Trimmed.StartsWith("#")) {
        continue
    }

    $Separator = $Trimmed.IndexOf("=")
    if ($Separator -lt 1) {
        continue
    }

    $Key = $Trimmed.Substring(0, $Separator).Trim()
    $Value = $Trimmed.Substring($Separator + 1)
    $EnvVars[$Key] = $Value
    Set-Item -Path "Env:$Key" -Value $Value
}

if (Get-Command docker -ErrorAction SilentlyContinue) {
    try {
        & docker compose version *> $null
        if ($LASTEXITCODE -eq 0) {
            & docker compose -f $ComposeFile up -d --build
            if ($LASTEXITCODE -ne 0) {
                throw "docker compose up failed."
            }
            & docker compose -f $ComposeFile ps
            if ($LASTEXITCODE -ne 0) {
                throw "docker compose ps failed."
            }
            Write-Host "API:       http://127.0.0.1:$(Get-EnvValueOrDefault -Map $EnvVars -Key 'HOST_API_PORT' -DefaultValue '8000')"
            Write-Host "Web:       http://127.0.0.1:$(Get-EnvValueOrDefault -Map $EnvVars -Key 'HOST_WEB_PORT' -DefaultValue '3000')"
            Write-Host "Streamlit: http://127.0.0.1:$(Get-EnvValueOrDefault -Map $EnvVars -Key 'HOST_STREAMLIT_PORT' -DefaultValue '8501')"
            exit 0
        }
    } catch {
    }
}

if (Get-Command docker-compose -ErrorAction SilentlyContinue) {
    $env:PYTHONNOUSERSITE = "1"
    & docker-compose -f $ComposeFile up -d --build
    if ($LASTEXITCODE -ne 0) {
        throw "docker-compose up failed."
    }
    & docker-compose -f $ComposeFile ps
    if ($LASTEXITCODE -ne 0) {
        throw "docker-compose ps failed."
    }
    Write-Host "API:       http://127.0.0.1:$(Get-EnvValueOrDefault -Map $EnvVars -Key 'HOST_API_PORT' -DefaultValue '8000')"
    Write-Host "Web:       http://127.0.0.1:$(Get-EnvValueOrDefault -Map $EnvVars -Key 'HOST_WEB_PORT' -DefaultValue '3000')"
    Write-Host "Streamlit: http://127.0.0.1:$(Get-EnvValueOrDefault -Map $EnvVars -Key 'HOST_STREAMLIT_PORT' -DefaultValue '8501')"
    exit 0
}

throw "docker compose was not found."
