$dir = 'e:\SERVER\Work_MEDIA\travels\_work\housing_yandex'
$py = (Get-Command python).Source
Start-Process -FilePath $py `
  -ArgumentList '-u', 'run_lists.py', '--rounds', '10' `
  -WorkingDirectory $dir `
  -RedirectStandardOutput (Join-Path $dir 'lists\console6.log') `
  -RedirectStandardError (Join-Path $dir 'lists\console6.err') `
  -WindowStyle Hidden
Start-Sleep -Seconds 3
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*run_lists.py*' } |
  ForEach-Object { Write-Output ("started pid " + $_.ProcessId) }
