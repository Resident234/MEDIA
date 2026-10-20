[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$E = Join-Path $env:APPDATA "npm\node_modules\agent-browser\bin\agent-browser-win32-x64.exe"
$S = "yxm"
$W = "travels\_work\fitness_yandex"

Get-Content "$W\yx_item.js" -Raw -Encoding UTF8 | & $E --session $S eval --stdin | Out-File -Encoding utf8 "$W\item_probe.txt"
Write-Output "saved item_probe.txt"
