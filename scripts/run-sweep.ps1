# Runs one sweep + digest. Called by Task Scheduler; safe to run by hand.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ("sweep-" + (Get-Date -Format "yyyy-MM") + ".log")
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
"$stamp sweep start" | Out-File -Append -Encoding utf8 $log
& "$root\.venv\Scripts\bid-radar.exe" sweep 2>&1 | Out-File -Append -Encoding utf8 $log
"$stamp sweep exit $LASTEXITCODE" | Out-File -Append -Encoding utf8 $log
