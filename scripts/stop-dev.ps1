# Stop the local dev services (API on 8000, web on 3000).
# PostgreSQL keeps running: the data lives in its container volume.
$ErrorActionPreference = 'Stop'

foreach ($port in 3000, 8000) {
    $lines = netstat -ano | Select-String (':' + $port + '\s')
    $stopped = 0
    foreach ($line in $lines) {
        $text = $line.ToString().Trim()
        if ($text -notmatch 'LISTENING') { continue }
        $parts = $text -split '\s+'
        $processId = $parts[-1]
        if ($processId -eq '0') { continue }
        $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($null -eq $proc) { continue }
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        Write-Host ('      stopped ' + $proc.ProcessName + ' (pid ' + $processId + ') on port ' + $port)
        $stopped++
    }
    if ($stopped -eq 0) { Write-Host ('      port ' + $port + ' was free') }
}
Write-Host 'services stopped.' -ForegroundColor Green