# Run the same commands GitHub Actions runs, locally.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/ci.ps1
# NOTE: keep this file ASCII-only (Windows PowerShell 5.1 reads BOM-less scripts as ANSI).
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$failures = @()

# npm ci deletes node_modules before reinstalling. While a dev server is running,
# next start holds node_modules/@next/swc-*.node open, so the unlink fails with
# EPERM and leaves the install (and the running site) broken. Refuse early.
$busy = @()
foreach ($port in 3000, 8000) {
  $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
  if ($conn) { $busy += $port }
}
if ($busy.Count -gt 0) {
  Write-Host ('Ports in use: ' + ($busy -join ', ')) -ForegroundColor Yellow
  Write-Host 'Stop the dev servers first (start-dev runs them). npm ci cannot replace node_modules while next start is running.' -ForegroundColor Yellow
  exit 1
}

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

Write-Host '=== docs ===' -ForegroundColor Cyan
Push-Location $root
Step 'docs consistency' { node scripts/docs-consistency-check.mjs | Out-Null }
Pop-Location

Write-Host '=== security ===' -ForegroundColor Cyan
Push-Location (Join-Path $root 'apps/web')
# Exit code 2 means the audit is unavailable (offline). That is not a failure, but it
# must be reported: a silently skipped security check is worse than a noisy one.
node scripts/audit-check.mjs
$auditExit = $LASTEXITCODE
Pop-Location
if ($auditExit -eq 0) {
  Write-Host '    ok: audit baseline' -ForegroundColor Green
} elseif ($auditExit -eq 2) {
  Write-Host '    skipped: audit unavailable (offline?)' -ForegroundColor Yellow
} else {
  Write-Host '    FAILED: audit baseline' -ForegroundColor Red
  $failures += 'audit baseline'
}

Write-Host '=== job: api ===' -ForegroundColor Cyan
Push-Location (Join-Path $root 'apps/api')
Step 'uv sync --locked' { uv sync --locked | Out-Null }
Step 'ruff check' { uv run ruff check app tests migrations }
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