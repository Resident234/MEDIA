$procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*run_lists.py*' }
if (-not $procs) { Write-Output 'not running'; exit 0 }
foreach ($p in $procs) {
  Write-Output ("pid " + $p.ProcessId + " " + $p.CommandLine)
  Stop-Process -Id $p.ProcessId -Force
}
Write-Output 'stopped'
