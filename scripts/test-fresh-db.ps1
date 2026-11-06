# Run both test suites against a throwaway database, exactly like CI does.
#
# Why: the integration suite is hermetic (each case builds its own fixtures), but the
# DEVELOPMENT database also holds real learning history - submissions, review items,
# plan rows from actual use. Running the suite against it can fail for reasons that
# have nothing to do with the code, and then it is unclear whether a red test means a
# regression or just leftover data. This script removes that ambiguity.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$dbName = 'copilot_ci_' + (Get-Random -Maximum 99999)

Push-Location (Join-Path $root 'apps/api')
try {
    Write-Host ('creating throwaway database ' + $dbName + ' ...') -ForegroundColor Cyan
    docker exec ai-learning-copilot-postgres psql -U copilot -d postgres -c ('CREATE DATABASE ' + $dbName) | Out-Null
    $env:DATABASE_URL = 'postgresql+asyncpg://copilot:copilot_dev_password@127.0.0.1:5432/' + $dbName
    uv run alembic upgrade head | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'alembic upgrade head failed' }

    Write-Host 'unit suite ...' -ForegroundColor Cyan
    uv run pytest -q
    $unit = $LASTEXITCODE

    Write-Host 'integration suite ...' -ForegroundColor Cyan
    uv run pytest -m integration -q
    $integration = $LASTEXITCODE
} finally {
    Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    docker exec ai-learning-copilot-postgres psql -U copilot -d postgres -c ('DROP DATABASE IF EXISTS ' + $dbName + ' WITH (FORCE)') | Out-Null
    Pop-Location
}

if ($unit -ne 0 -or $integration -ne 0) {
    Write-Host 'FAILED' -ForegroundColor Red
    exit 1
}
Write-Host 'both suites passed on a fresh database (same as CI).' -ForegroundColor Green