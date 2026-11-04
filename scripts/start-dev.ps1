# AI Learning Copilot - one-click local start (Windows PowerShell)
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/start-dev.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Write-Host '[1/4] checking docker ...' -ForegroundColor Cyan
$v = docker info --format '{{.ServerVersion}}' 2>$null
if (-not $v) { throw 'Docker is not running. Start Docker Desktop first.' }
Write-Host ('      docker ' + $v)

Write-Host '[2/4] starting postgres ...' -ForegroundColor Cyan
Push-Location $root
docker compose -f infra/docker-compose.yml up -d | Out-Null
$ok = $false
for ($i = 0; $i -lt 40; $i++) {
  $st = docker inspect --format '{{.State.Health.Status}}' ai-learning-copilot-postgres 2>$null
  if ($st -eq 'healthy') { $ok = $true; break }
  Start-Sleep -Seconds 2
}
if (-not $ok) { throw 'postgres did not become healthy in 80s' }
Write-Host '      postgres healthy on 127.0.0.1:5432' -ForegroundColor Green

Write-Host '[3/4] migrating and starting api on 127.0.0.1:8000 ...' -ForegroundColor Cyan
Push-Location (Join-Path $root 'apps\api')
uv run alembic upgrade head | Out-Null
Start-Process -FilePath 'uv' -ArgumentList 'run','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory (Get-Location) -WindowStyle Hidden
Pop-Location

Write-Host '[4/4] building and starting web on 127.0.0.1:3000 ...' -ForegroundColor Cyan
Push-Location (Join-Path $root 'apps\web')
if (-not (Test-Path '.next')) { npm run build | Out-Null }
Start-Process -FilePath 'npm' -ArgumentList 'run','start' -WorkingDirectory (Get-Location) -WindowStyle Hidden
Pop-Location
Pop-Location

Write-Host 'waiting for services ...' -ForegroundColor Cyan
$apiOk = $false; $webOk = $false
for ($i = 0; $i -lt 40; $i++) {
  if (-not $apiOk) { try { $apiOk = (Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/api/v1/health' -TimeoutSec 2).StatusCode -eq 200 } catch {} }
  if (-not $webOk) { try { $webOk = (Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:3000/' -TimeoutSec 2).StatusCode -eq 200 } catch {} }
  if ($apiOk -and $webOk) { break }
  Start-Sleep -Seconds 2
}
Write-Host ("API  : " + $(if ($apiOk) { 'OK http://127.0.0.1:8000/docs' } else { 'NOT READY' }))
Write-Host ("WEB  : " + $(if ($webOk) { 'OK http://127.0.0.1:3000' } else { 'NOT READY' }))
if (-not ($apiOk -and $webOk)) { throw 'services not ready in 80s' }
Write-Host 'started. run ./scripts/smoke.ps1 to verify.' -ForegroundColor Green