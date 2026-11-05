# AI Learning Copilot - smoke test (read-only, no business writes)
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/smoke.ps1
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$fail = 0

# An exported DATABASE_URL overrides apps/api/.env, so a leftover value from an
# earlier shell session (for example a dropped temporary database) makes every
# alembic check fail for a reason that has nothing to do with the repository.
if ($env:DATABASE_URL) {
  $masked = $env:DATABASE_URL -replace '://[^@]*@', '://***@'
  Write-Host ('NOTE  shell DATABASE_URL is set and overrides .env: ' + $masked) -ForegroundColor Yellow
}
function Check($name, [scriptblock]$test) {
  try { $r = & $test; if ($r) { Write-Host ('PASS  ' + $name) -ForegroundColor Green } else { Write-Host ('FAIL  ' + $name) -ForegroundColor Red; $script:fail++ } }
  catch { Write-Host ('FAIL  ' + $name + ' -> ' + $_.Exception.Message) -ForegroundColor Red; $script:fail++ }
}
Write-Host '=== 1. database ===' -ForegroundColor Cyan
Check 'postgres healthy' { (docker inspect --format '{{.State.Health.Status}}' ai-learning-copilot-postgres) -eq 'healthy' }
Check 'postgres bound to 127.0.0.1:5432' { ((docker port ai-learning-copilot-postgres 5432) -join ',') -match '127.0.0.1' }
Push-Location (Join-Path $root 'apps\api')
Check 'alembic at head' { (uv run alembic current 2>$null) -match '\(head\)' }
Pop-Location

Write-Host '=== 2. api ===' -ForegroundColor Cyan
Check 'health 200' { (Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8000/api/v1/health' -TimeoutSec 5).StatusCode -eq 200 }
# The running API can be an older process than the checkout: start it, change the
# version, and /health keeps reporting the old number because nothing restarted it.
# This happened three times in one session, so it is checked rather than remembered.
Check 'running API version matches pyproject' {
  $pyproject = Join-Path $root 'apps/api/pyproject.toml'
  $expected = (Select-String -Path $pyproject -Pattern '^version = "([^"]+)"').Matches[0].Groups[1].Value
  $actual = (Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/health' -TimeoutSec 5).version
  if ($actual -ne $expected) { Write-Host ('      expected ' + $expected + ', running ' + $actual + ' -> restart the API') -ForegroundColor Yellow }
  $actual -eq $expected
}
Check 'ready connected' { (Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8000/api/v1/ready' -TimeoutSec 5).Content -match 'connected' }
Check 'skills = 6' { ((Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/skills' -TimeoutSec 5).skills).Count -eq 6 }
Check 'lessons >= 5' { ((Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/lessons' -TimeoutSec 5).items).Count -ge 5 }
Check 'exercises >= 10' { ((Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/exercises' -TimeoutSec 5).items).Count -ge 10 }
Check 'diagnostics paper 20 items, no answer keys' { $p = Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/diagnostics/paper' -TimeoutSec 5; ($p.total -eq 20) -and (($p.questions | ConvertTo-Json -Depth 5) -notmatch 'answer|correct') }
Check 'study-plan shape has budget fields' { $s = Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/study-plan' -TimeoutSec 5; ($null -ne $s.scheduled_items) -and ($null -ne $s.history_items) }

Write-Host '=== 3. web ===' -ForegroundColor Cyan
foreach ($p in @('/','/learn','/onboarding','/diagnostic','/result','/plan','/history','/practice')) {
  $path = $p
  Check ('page ' + $path + ' -> 200') { (Invoke-WebRequest -UseBasicParsing ('http://127.0.0.1:3000' + $path) -TimeoutSec 5).StatusCode -eq 200 }
}

Write-Host ''
if ($fail -eq 0) { Write-Host 'SMOKE OK - all checks passed' -ForegroundColor Green; exit 0 }
else { Write-Host ('SMOKE FAILED - failures: ' + $fail) -ForegroundColor Red; exit 1 }