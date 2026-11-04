# Run the same commands GitHub Actions runs, locally.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/ci.ps1
# NOTE: keep this file ASCII-only (Windows PowerShell 5.1 reads BOM-less scripts as ANSI).
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$failures = @()

function Step($name, [scriptblock]$run) {
  Write-Host ('--- ' + $name) -ForegroundColor Cyan
  & $run
  if ($LASTEXITCODE -ne 0) {
    Write-Host ('    FAILED: ' + $name + ' (exit ' + $LASTEXITCODE + ')') -ForegroundColor Red
    $script:failures += $name
  } else {
    Write-Host ('    ok: ' + $name) -ForegroundColor Green
  }
}

Write-Host '=== job: api ===' -ForegroundColor Cyan
Push-Location (Join-Path $root 'apps/api')
Step 'uv sync --locked' { uv sync --locked | Out-Null }
Step 'ruff check' { uv run ruff check app tests }
Step 'alembic upgrade head' { uv run alembic upgrade head | Out-Null }
Step 'alembic current reports head' {
  $out = uv run alembic current 2>&1 | Out-String
  if ($out -match '\(head\)') { $global:LASTEXITCODE = 0 } else { $global:LASTEXITCODE = 1 }
}
Step 'pytest (unit)' { uv run pytest -q }
Step 'pytest (integration)' { uv run pytest -q -m integration }
Pop-Location

Write-Host '=== job: web ===' -ForegroundColor Cyan
Push-Location (Join-Path $root 'apps/web')
Step 'npm ci' { npm ci --no-audit --no-fund | Out-Null }
Step 'tsc --noEmit' { npx tsc --noEmit }
Step 'npm run lint' { npm run lint }
Step 'npm run build' { npm run build | Out-Null }
Pop-Location

Write-Host ''
if ($failures.Count -eq 0) {
  Write-Host 'CI-equivalent checks passed.' -ForegroundColor Green
  exit 0
}
Write-Host ('CI-equivalent checks FAILED: ' + ($failures -join ', ')) -ForegroundColor Red
exit 1