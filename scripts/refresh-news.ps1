# Refresh the research column once. Intended for Windows Task Scheduler.
#
# The app never schedules network calls on its own: fetching is an explicit action.
# This script is that action, so a periodic refresh is a scheduled task you can see
# and disable from the OS, rather than a timer hidden inside the API process.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\refresh-news.ps1
#
# Register it hourly:
#   schtasks /create /tn "AI Learning Copilot - news" /sc hourly ^
#     /tr "powershell -NoProfile -ExecutionPolicy Bypass -File <REPO>/scripts/refresh-news.ps1"
#
# Replace <REPO> with this checkout's absolute path (it contains Chinese characters,
# which is why the example cannot spell it out in an ASCII-only script).
#
# Remove it:
#   schtasks /delete /tn "AI Learning Copilot - news" /f
$ErrorActionPreference = 'Stop'
$api = 'http://127.0.0.1:8000/api/v1/news/refresh'

try {
    $response = Invoke-RestMethod -Method Post -Uri $api -TimeoutSec 120
} catch {
    Write-Host ('refresh failed: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}

foreach ($stat in $response.sources) {
    if ($stat.status -eq 'ok') {
        Write-Host ('  ' + $stat.source + ': fetched ' + $stat.fetched + ', inserted ' + $stat.inserted)
    } else {
        Write-Host ('  ' + $stat.source + ': ' + $stat.status + ' (' + $stat.detail + ')') -ForegroundColor Yellow
    }
}
Write-Host ('items ' + $response.items_before + ' -> ' + $response.items_after) -ForegroundColor Green
