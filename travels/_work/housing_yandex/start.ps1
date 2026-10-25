# Launch the nationwide housing crawl detached: supervisor restarts run_lists
# after a crash, lists/*.jsonl make the restart a continuation.
$dir = 'e:\SERVER\Work_MEDIA\travels\_work\housing_yandex'
$py = (Get-Command python).Source
# Свежий профиль: старый сеанс yxhousing сидит за заглушкой «limited».
$env:YX_SESSION = 'yxfresh1'
# Выдача берётся обычным HTTP: серверная страница Карт отдаёт весь
# state-view, а браузер на частых запросах получает заглушку.
$env:YX_TRANSPORT = 'http'
Start-Process -FilePath $py `
  -ArgumentList '-u', 'supervise.py', '--rounds', '40' `
  -WorkingDirectory $dir `
  -RedirectStandardOutput (Join-Path $dir 'lists\console.log') `
  -RedirectStandardError (Join-Path $dir 'lists\console.err') `
  -WindowStyle Hidden
Start-Sleep -Seconds 3
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*supervise.py*' -or $_.CommandLine -like '*run_lists.py*' } |
  ForEach-Object { Write-Output ("started pid " + $_.ProcessId + " : " + $_.CommandLine) }
