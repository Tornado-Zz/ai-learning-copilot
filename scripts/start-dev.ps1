# AI Learning Copilot - one-click local start (Windows PowerShell)
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/start-dev.ps1
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads a BOM-less script as
# ANSI, so any non-ASCII character breaks string literals at parse time.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

Write-Host '[1/5] checking docker ...' -ForegroundColor Cyan
# docker.exe reports failure on stderr; with ErrorActionPreference=Stop that raises
# NativeCommandError before our message can run. Relax it for this probe only.
$prev = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$v = docker info --format '{{.ServerVersion}}' 2>$null
$dockerExit = $LASTEXITCODE
$ErrorActionPreference = $prev
if ($dockerExit -ne 0 -or -not $v) {
  Write-Host '      Docker is not running. Start Docker Desktop, wait until it is ready, then run this script again.' -ForegroundColor Yellow
  exit 1
}
Write-Host ('      docker ' + $v)

Write-Host '[2/5] preparing env files ...' -ForegroundColor Cyan
# A fresh clone has no .env files: only the .env.example templates are committed and the
# real files are gitignored. The backend works on defaults, but the AI tutor needs
# DEEPSEEK_API_KEY, so create an editable copy on first run.
$pairs = @(
  @{ Example = Join-Path $root 'apps/api/.env.example'; Target = Join-Path $root 'apps/api/.env' },
  @{ Example = Join-Path $root 'apps/web/.env.example'; Target = Join-Path $root 'apps/web/.env.local' }
)
foreach ($pair in $pairs) {
  if ((-not (Test-Path $pair.Target)) -and (Test-Path $pair.Example)) {
    Copy-Item $pair.Example $pair.Target
    Write-Host ('      created ' + $pair.Target)
  }
}

Write-Host '[3/5] starting postgres ...' -ForegroundColor Cyan
Push-Location $root
docker compose -f infra/docker-compose.yml up -d | Out-Null
$ok = $false
for ($i = 0; $i -lt 40; $i++) {
  $st = docker inspect --format '{{.State.Health.Status}}' ai-learning-copilot-postgres 2>$null
  if ($st -eq 'healthy') { $ok = $true; break }
  Start-Sleep -Seconds 2
}
if (-not $ok) { Pop-Location; throw 'postgres did not become healthy in 80s' }
Write-Host '      postgres healthy on 127.0.0.1:5432' -ForegroundColor Green

Write-Host '[4/5] migrating and starting api on 127.0.0.1:8000 ...' -ForegroundColor Cyan
Push-Location (Join-Path $root 'apps/api')
uv run alembic upgrade head | Out-Null
Start-Process -FilePath 'uv' -ArgumentList 'run','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory (Get-Location) -WindowStyle Hidden
Pop-Location

Write-Host '[5/5] building and starting web on 127.0.0.1:3000 ...' -ForegroundColor Cyan
Push-Location (Join-Path $root 'apps/web')
# A fresh clone has no node_modules; without this the build dies with
# "'next' is not recognized as an internal or external command".
if (-not (Test-Path 'node_modules')) {
  Write-Host '      first run: installing web dependencies (npm ci) ...' -ForegroundColor Yellow
  npm ci | Out-Null
  if ($LASTEXITCODE -ne 0) { Pop-Location; Pop-Location; throw 'npm ci failed' }
}
if (-not (Test-Path '.next')) {
  Write-Host '      first run: building the frontend, this takes a few minutes ...' -ForegroundColor Yellow
  npm run build | Out-Null
  if ($LASTEXITCODE -ne 0) { Pop-Location; Pop-Location; throw 'npm run build failed' }
}
# Start-Process cannot launch 'npm' directly: on Windows npm is a .cmd wrapper, and
# Start-Process reports success while nothing actually runs. Go through cmd.exe and
# keep a log so a failed start is diagnosable instead of silent.
Start-Process -FilePath 'cmd.exe' -ArgumentList '/c','npm run start > web-start.log 2>&1' -WorkingDirectory (Get-Location) -WindowStyle Hidden
Pop-Location
Pop-Location

Write-Host 'waiting for services ...' -ForegroundColor Cyan
$apiOk = $false
$webOk = $false
for ($i = 0; $i -lt 60; $i++) {
  if (-not $apiOk) { try { $apiOk = (Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/api/v1/health' -TimeoutSec 2).StatusCode -eq 200 } catch {} }
  if (-not $webOk) { try { $webOk = (Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:3000/' -TimeoutSec 2).StatusCode -eq 200 } catch {} }
  if ($apiOk -and $webOk) { break }
  Start-Sleep -Seconds 2
}
Write-Host ("API  : " + $(if ($apiOk) { 'OK http://127.0.0.1:8000/docs' } else { 'NOT READY' }))
Write-Host ("WEB  : " + $(if ($webOk) { 'OK http://127.0.0.1:3000' } else { 'NOT READY' }))
if (-not ($apiOk -and $webOk)) { throw 'services not ready in 120s' }
Write-Host 'started. run ./scripts/smoke.ps1 to verify.' -ForegroundColor Green