$ErrorActionPreference = 'Stop'
$cacheRoot = Split-Path $PSScriptRoot -Parent
$cacheConfigPath = Join-Path $cacheRoot 'data\redis-cache.json'
if (-not (Test-Path -LiteralPath $cacheConfigPath)) { return }
$cacheConfig = Get-Content -LiteralPath $cacheConfigPath -Raw | ConvertFrom-Json
if (-not $cacheConfig.autostart) { return }
$cacheExe = [IO.Path]::GetFullPath($cacheConfig.executable)
$cacheAllowed = [IO.Path]::GetFullPath((Join-Path $cacheRoot '.tools\redis')) + [IO.Path]::DirectorySeparatorChar
if (-not $cacheExe.StartsWith($cacheAllowed, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected Redis executable path' }
if ((Get-FileHash -LiteralPath $cacheExe -Algorithm SHA256).Hash -ne $cacheConfig.executable_sha256) { throw 'Redis executable checksum mismatch' }
$cacheListener = Get-NetTCPConnection -LocalPort 6379 -State Listen -ErrorAction SilentlyContinue
if ($cacheListener) {
    $cacheExisting = Get-CimInstance Win32_Process -Filter "ProcessId=$($cacheListener.OwningProcess)"
    if ($cacheExisting.ExecutablePath -ne $cacheExe) { throw 'Port 6379 belongs to another service; it was not changed' }
    return
}
$cacheData = Join-Path $cacheRoot 'data\redis'
$cacheLogs = Join-Path $cacheRoot 'data\logs'
New-Item -ItemType Directory -Path $cacheData,$cacheLogs -Force | Out-Null
$cacheConf = Join-Path $cacheData 'redis.conf'
$cachePosixData = $cacheData.Replace('\','/')
$cacheText = @"
bind 127.0.0.1
protected-mode yes
port 6379
save ""
appendonly no
maxmemory 64mb
maxmemory-policy allkeys-lru
maxclients 256
dir "$cachePosixData"
"@
[IO.File]::WriteAllText($cacheConf, $cacheText, (New-Object System.Text.UTF8Encoding($false)))
$cacheProcess = Start-Process -FilePath $cacheExe -ArgumentList @('redis.conf') -WorkingDirectory $cacheData -WindowStyle Hidden -RedirectStandardOutput (Join-Path $cacheLogs 'redis.out.log') -RedirectStandardError (Join-Path $cacheLogs 'redis.err.log') -PassThru
$cacheProcess.Id | Set-Content -LiteralPath (Join-Path $cacheData 'redis.pid')
$cacheReady = $false
$cacheCli = Join-Path (Split-Path $cacheExe -Parent) 'redis-cli.exe'
for ($cacheAttempt = 0; $cacheAttempt -lt 20; $cacheAttempt++) {
    $cachePong = & $cacheCli -h 127.0.0.1 -p 6379 PING 2>$null
    if ($LASTEXITCODE -eq 0 -and $cachePong -eq 'PONG') { $cacheReady = $true; break }
    Start-Sleep -Milliseconds 250
}
if (-not $cacheReady) { throw 'Redis did not become ready; check data/logs/redis.err.log' }
Write-Output 'Project Redis cache started on 127.0.0.1:6379 (64MB, no persistence).'
