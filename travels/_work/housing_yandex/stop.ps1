# Stop the crawl. Order matters: the supervisor goes first, otherwise it
# restarts run_lists five minutes later.
$procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*supervise.py*' -or $_.CommandLine -like '*run_lists.py*' }
if (-not $procs) { Write-Output 'not running'; exit 0 }
foreach ($p in ($procs | Sort-Object { if ($_.CommandLine -like '*supervise.py*') { 0 } else { 1 } })) {
  Write-Output ("pid " + $p.ProcessId + " " + $p.CommandLine)
  Stop-Process -Id $p.ProcessId -Force
}
Write-Output 'stopped'
