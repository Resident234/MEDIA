param(
  [Parameter(Mandatory=$true)][string]$Url,
  [string]$Session = 'yxm'
)
$E = Join-Path $env:APPDATA 'npm\node_modules\agent-browser\bin\agent-browser-win32-x64.exe'
& $E --session $Session open $Url
Write-Output "EXIT=$LASTEXITCODE"
