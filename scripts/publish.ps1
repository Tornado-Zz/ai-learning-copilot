# Publish this repository to a (pre-created, empty) GitHub repository.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\publish.ps1 -RepoUrl https://github.com/<you>/<repo>.git
#
# It refuses to run when the working tree is dirty or when any commit in history
# looks like it contains a real API key, and it never force-pushes.
param(
    [Parameter(Mandatory = $true)][string]$RepoUrl,
    [switch]$SkipTests
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Fail($message) {
    Write-Host ('ABORT  ' + $message) -ForegroundColor Red
    exit 1
}

# Transport check. On some networks github.com:443 is unreachable while SSH (22 or
# 443) still works, so an https URL fails after a 20s timeout with no explanation.
# Detect it up front and tell the operator which remote form will actually work.
function Test-HttpsGitHub {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $task = $client.ConnectAsync('github.com', 443)
        $ok = $task.Wait(5000) -and $client.Connected
        $client.Close()
        return $ok
    } catch {
        return $false
    }
}
function Test-SshGitHub {
    $out = & ssh -o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout=6 -T git@github.com 2>&1
    $text = ($out | Out-String)
    return ($text -match 'successfully authenticated') -or ($text -match 'Permission denied \(publickey\)')
}

Write-Host '=== 0. transport to github.com ===' -ForegroundColor Cyan
$httpsOk = Test-HttpsGitHub
$sshOk = Test-SshGitHub
Write-Host ('    https 443 : ' + $(if ($httpsOk) { 'reachable' } else { 'NOT reachable' }))
Write-Host ('    ssh       : ' + $(if ($sshOk) { 'reachable' } else { 'NOT reachable' }))
if (-not $httpsOk -and -not $sshOk) {
    Fail 'this machine cannot reach github.com over either https or ssh; push from a machine that can'
}

$usingHttps = $RepoUrl -match '^https://'
if ($usingHttps -and -not $httpsOk) {
    $sshUrl = $RepoUrl -replace '^https://github\.com/', 'git@github.com:'
    Fail ('https to github.com is unreachable from this machine (ssh works). Use the SSH form instead:' + [Environment]::NewLine + '       ' + $sshUrl)
}
if (-not $usingHttps) {
    $keyFiles = @(Get-ChildItem -Path (Join-Path $HOME '.ssh') -Filter 'id_*' -ErrorAction SilentlyContinue)
    if ($keyFiles.Count -eq 0) {
        Write-Host '    NOTE: no SSH key found in ~/.ssh. Create one and add the public half to GitHub:' -ForegroundColor Yellow
        Write-Host '      ssh-keygen -t ed25519 -C "your@email"' -ForegroundColor Yellow
    }
}

Write-Host '=== 1. repository state ===' -ForegroundColor Cyan
$dirty = (git status --porcelain -uall | Measure-Object -Line).Lines
if ($dirty -ne 0) { Fail ('working tree is not clean (' + $dirty + ' entries); commit or stash first') }
$commits = (git rev-list --count HEAD).Trim()
$tags = (git tag | Measure-Object -Line).Lines
Write-Host ('    commits=' + $commits + ' tags=' + $tags)

Write-Host '=== 2. secret scan over the whole history ===' -ForegroundColor Cyan
$hits = (git log -p --all | Select-String -Pattern 'sk-[a-f0-9]{20,}' -AllMatches | Measure-Object -Line).Lines
if ($hits -ne 0) { Fail ('found ' + $hits + ' lines that look like API keys in history; rotate the key and rewrite history before publishing') }
Write-Host '    0 hits'

Write-Host '=== 3. documentation consistency ===' -ForegroundColor Cyan
node scripts/docs-consistency-check.mjs
if ($LASTEXITCODE -ne 0) { Fail 'docs consistency check failed' }

if (-not $SkipTests) {
    Write-Host '=== 4. unit tests (no database needed) ===' -ForegroundColor Cyan
    Push-Location (Join-Path $root 'apps/api')
    uv run pytest -q
    $code = $LASTEXITCODE
    Pop-Location
    if ($code -ne 0) { Fail 'unit tests failed' }
} else {
    Write-Host '=== 4. unit tests skipped (-SkipTests) ===' -ForegroundColor Yellow
}

Write-Host '=== 5. remote ===' -ForegroundColor Cyan
# List remotes instead of calling get-url: with no remote, get-url writes to stderr,
# and $ErrorActionPreference='Stop' turns that into a fatal error before the push step.
$remotes = @(git remote)
if ($remotes -contains 'origin') {
    $existing = (git remote get-url origin)
    Write-Host ('    replacing existing origin: ' + $existing)
    git remote remove origin
}
git remote add origin $RepoUrl
Write-Host ('    origin -> ' + $RepoUrl)

Write-Host '=== 6. push (never forced) ===' -ForegroundColor Cyan
git push -u origin main
if ($LASTEXITCODE -ne 0) { Fail 'push of main failed; the remote repository must already exist and be empty' }
git push origin --tags
if ($LASTEXITCODE -ne 0) { Fail 'push of tags failed' }

Write-Host ''
Write-Host '=== done. verify these three things on GitHub ===' -ForegroundColor Green
Write-Host ('  [ ] the repository lists ' + $tags + ' tags (v0.1.0 ... latest)')
Write-Host '  [ ] Actions: both jobs (api, web) are green'
Write-Host '  [ ] README shows all six screenshots from docs/images/'
Write-Host ''
Write-Host 'If CI fails on its first run, run scripts/ci.ps1 locally first:'
Write-Host 'it executes the same commands and reproduces the failure without a round trip.'