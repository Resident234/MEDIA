[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$E = Join-Path $env:APPDATA "npm\node_modules\agent-browser\bin\agent-browser-win32-x64.exe"
$S = "yxm"
$Q = "%D0%A2%D1%80%D0%B5%D0%BD%D0%B0%D0%B6%D0%B5%D1%80%D0%BD%D1%8B%D0%B9%20%D0%B7%D0%B0%D0%BB"
$url = "https://yandex.ru/maps/?ll=68.7870,38.5598&z=12&text=" + $Q

& $E --session $S close 2>$null | Out-Null
& $E --session $S --headed --restore open $url
Start-Sleep -Seconds 12

Write-Output "HREF: $(& $E --session $S eval 'location.href')"
Write-Output "TITLE: $(& $E --session $S eval 'document.title')"
$cap = & $E --session $S eval "location.href.indexOf('showcaptcha') >= 0"
Write-Output "CAPTCHA: $cap"
Write-Output "IFRAMES: $(& $E --session $S eval 'window.frames.length')"
