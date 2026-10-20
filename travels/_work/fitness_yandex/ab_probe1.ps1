[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$E = Join-Path $env:APPDATA "npm\node_modules\agent-browser\bin\agent-browser-win32-x64.exe"
$S = "yxm"
$W = "travels\_work\fitness_yandex"
$out = "$W\probe1.txt"

& $E --session $S eval "location.href" | Out-File -Encoding utf8 $out
Get-Content "$W\yx_struct.js" -Raw -Encoding UTF8 | & $E --session $S eval --stdin | Out-File -Encoding utf8 -Append $out
& $E --session $S eval "document.body.innerText.slice(0,900)" | Out-File -Encoding utf8 -Append $out
Write-Output "saved: $out"
