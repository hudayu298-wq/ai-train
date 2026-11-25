param([switch]$Foreground)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
try { & (Join-Path $PSScriptRoot 'scripts\start_redis.ps1') }
catch { Write-Warning 'Local Redis startup failed; backend will use its database/file fallback.' }
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    throw '请先按 README 创建 Python 虚拟环境并安装后端依赖。'
}
if ($Foreground) {
    & '.\.venv\Scripts\python.exe' -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
    exit $LASTEXITCODE
}
$fitnessListener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($fitnessListener) {
    $fitnessHealth = Invoke-RestMethod 'http://127.0.0.1:8000/api/health' -TimeoutSec 5
    if ($fitnessHealth.mode -ne 'multi_user') {
        throw '8000 端口仍运行旧版后端或其他服务。请停止旧版 LiftLab 后端后重新启动。'
    }
} else {
    $fitnessLogs = Join-Path $PSScriptRoot 'data\logs'
    New-Item -ItemType Directory -Path $fitnessLogs -Force | Out-Null
    $fitnessProcess = Start-Process -FilePath (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') -ArgumentList @('-m', 'uvicorn', 'backend.app:app', '--host', '127.0.0.1', '--port', '8000') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $fitnessLogs 'server.out.log') -RedirectStandardError (Join-Path $fitnessLogs 'server.err.log') -PassThru
    $fitnessProcess.Id | Set-Content (Join-Path $PSScriptRoot 'data\server.pid')
    $fitnessReady = $false
    for ($fitnessAttempt = 0; $fitnessAttempt -lt 20; $fitnessAttempt++) {
        try {
            $fitnessHealth = Invoke-RestMethod 'http://127.0.0.1:8000/api/health' -TimeoutSec 1
            if ($fitnessHealth.status -eq 'ok') { $fitnessReady = $true; break }
        } catch { Start-Sleep -Milliseconds 250 }
    }
    if (-not $fitnessReady) { throw "启动失败，请检查 $fitnessLogs\server.err.log" }
}
Write-Output 'LiftLab 后台服务已运行。'
Write-Output 'Flutter 预览：http://127.0.0.1:8000/app/'
Write-Output '入口（跳转登录页）：http://127.0.0.1:8000/'
