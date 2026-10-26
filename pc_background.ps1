param([ValidateSet('start','stop')][string]$Action='start')
$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$state=Join-Path $root 'work\background-processes.json'
if ($Action -eq 'stop') {
    if (Test-Path -LiteralPath $state) {
        $saved=Get-Content -LiteralPath $state -Raw | ConvertFrom-Json
        foreach ($entry in $saved) {
            $process=Get-Process -Id $entry.id -ErrorAction SilentlyContinue
            if ($process -and $process.StartTime.ToUniversalTime().Ticks.ToString() -eq $entry.started -and $process.Path -eq $entry.path) { Stop-Process -Id $entry.id }
        }
        Remove-Item -LiteralPath $state
    }
    exit
}
if (Test-Path -LiteralPath $state) { throw 'Background state exists. Run stop first, then start again.' }
if (Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 8080 is in use. Close the old backend CMD before starting.' }
$python=Join-Path $root '.venv\Scripts\python.exe'
$tunnel=Get-Command cloudflared.exe -ErrorAction Stop
$env:HOST='127.0.0.1'; $env:PORT='8080'
$env:FRIDGE_DATA_DIR=Join-Path $root 'work\cloud-data'
$env:HF_HOME=Join-Path $root 'work\models\huggingface'
# Playwright uses its default installation location.
# Allowed origins are loaded from work/local-config.json by the launcher.
$env:FRIDGE_ACCESS_TOKEN=(Get-Content -LiteralPath (Join-Path $root 'work\access-token.txt') -Raw).Trim()
$started=@()
try {
    $backend=Start-Process -FilePath $python -ArgumentList 'run_pc_backend.py' -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput (Join-Path $root 'work\backend.log') -RedirectStandardError (Join-Path $root 'work\backend-errors.log') -PassThru
    $started+=$backend
    $ready=$false
    for ($i=0;$i -lt 30;$i++) {
        if ($backend.HasExited) { throw 'Backend stopped; inspect work\backend-errors.log.' }
        try { if ((Invoke-RestMethod 'http://127.0.0.1:8080/api/health' -TimeoutSec 2).status -eq 'ok') { $ready=$true; break } } catch { Start-Sleep -Seconds 1 }
    }
    if (!$ready) { throw 'Backend health check failed.' }
    $connector=Start-Process -FilePath $tunnel.Source -ArgumentList 'tunnel','--url','http://127.0.0.1:8080' -WindowStyle Hidden -RedirectStandardOutput (Join-Path $root 'work\tunnel.log') -RedirectStandardError (Join-Path $root 'work\tunnel-errors.log') -PassThru
    $started+=$connector
    @($started | ForEach-Object { @{id=$_.Id; started=$_.StartTime.ToUniversalTime().Ticks.ToString();path=$_.Path} }) | ConvertTo-Json | Set-Content -LiteralPath $state -Encoding UTF8
    for ($i=0;$i -lt 45;$i++) {
        if ($connector.HasExited) { throw 'Tunnel stopped; inspect work\tunnel-errors.log.' }
        $text=Get-Content -LiteralPath (Join-Path $root 'work\tunnel-errors.log') -Raw -ErrorAction SilentlyContinue
        if ($text -match 'https://[a-z0-9-]+\.trycloudflare\.com') {
            $Matches[0] | Set-Content -LiteralPath (Join-Path $root 'work\phone-address.txt') -Encoding ASCII
            & $python (Join-Path $root 'publish_address.py')
            if ($LASTEXITCODE -ne 0) { Write-Warning 'Automatic address registration failed; backend is still running.' }
            exit
        }
        Start-Sleep -Seconds 1
    }
    throw 'No tunnel address received; inspect tunnel logs.'
} catch {
    $_.Exception.Message | Set-Content -LiteralPath (Join-Path $root 'work\background-error.txt') -Encoding UTF8
    $started | ForEach-Object { if (!$_.HasExited) { Stop-Process -Id $_.Id } }
    if (Test-Path -LiteralPath $state) { Remove-Item -LiteralPath $state }
    throw
}
