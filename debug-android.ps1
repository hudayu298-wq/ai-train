param(
    [string]$SdkPath,
    [string]$DeviceId
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$fitnessFlutter = Join-Path $PSScriptRoot '.tools\flutter\bin\flutter.bat'
$fitnessCandidates = @($SdkPath, (Join-Path $PSScriptRoot '.tools\android-sdk'), $env:ANDROID_HOME, $env:ANDROID_SDK_ROOT, (Join-Path $env:LOCALAPPDATA 'Android\Sdk'))
$fitnessSdk = $fitnessCandidates | Where-Object { $_ -and (Test-Path (Join-Path $_ 'platform-tools\adb.exe')) } | Select-Object -First 1
if (-not $fitnessSdk) {
    throw '没有找到Android SDK。先安装Android Studio及SDK Platform-Tools；自定义安装位置请传入 -SdkPath。'
}
$fitnessAdb = Join-Path $fitnessSdk 'platform-tools\adb.exe'
& $fitnessFlutter config --android-sdk $fitnessSdk
if ($LASTEXITCODE -ne 0) { throw 'Flutter SDK路径配置失败。' }
$fitnessDeviceOutput = & $fitnessAdb devices
if ($LASTEXITCODE -ne 0) { throw 'ADB运行失败。' }
$fitnessDevices = @($fitnessDeviceOutput | ForEach-Object {
    if ($_ -match '^(\S+)\s+device\s*$') { $Matches[1] }
})
if ($DeviceId) {
    if ($DeviceId -notin $fitnessDevices) { throw '指定手机未授权或未连接。请检查USB调试、数据线和手机授权提示。' }
    $fitnessDevice = $DeviceId
} elseif ($fitnessDevices.Count -eq 1) {
    $fitnessDevice = $fitnessDevices[0]
} elseif ($fitnessDevices.Count -gt 1) {
    throw ('发现多个设备，请用 -DeviceId 指定：' + ($fitnessDevices -join ', '))
} else {
    $fitnessDeviceOutput | Write-Output
    throw '未找到已授权设备。请连接数据线、开启USB调试并在手机确认允许调试；unauthorized表示尚未授权。'
}
& (Join-Path $PSScriptRoot 'start.ps1')
& $fitnessAdb -s $fitnessDevice reverse tcp:8000 tcp:8000
if ($LASTEXITCODE -ne 0) { throw '手机到本地后端的端口转发失败。' }
Write-Output 'USB后端转发已开启。手机App通过127.0.0.1:8000连接本机后端。'
# Some Honor devices suppress all log tags, hiding the Dart VM service announcement.
# This non-persistent, Flutter-only override enables debugger discovery until reboot.
$fitnessLogLevel = (& $fitnessAdb -s $fitnessDevice shell getprop persist.log.tag).Trim()
if ($fitnessLogLevel -eq 'S') {
    & $fitnessAdb -s $fitnessDevice shell setprop log.tag.flutter I
    if ($LASTEXITCODE -ne 0) { throw '无法开启Flutter调试日志。' }
}
$fitnessPreviousJavaOptions = $env:JAVA_TOOL_OPTIONS
# Gradle does not automatically read the HTTP_PROXY/HTTPS_PROXY environment variables.
if ($env:HTTPS_PROXY) {
    $fitnessProxy = [uri]$env:HTTPS_PROXY
    if ($fitnessProxy.Scheme -eq 'http' -and -not $fitnessProxy.UserInfo) {
        $fitnessProxyOptions = '-Dhttps.proxyHost={0} -Dhttps.proxyPort={1} -Dhttp.proxyHost={0} -Dhttp.proxyPort={1} -Dhttp.nonProxyHosts=localhost|127.*' -f $fitnessProxy.Host, $fitnessProxy.Port
        $env:JAVA_TOOL_OPTIONS = ($fitnessPreviousJavaOptions + ' ' + $fitnessProxyOptions).Trim()
    }
}
Push-Location (Join-Path $PSScriptRoot 'mobile')
try {
    & $fitnessFlutter pub get
    if ($LASTEXITCODE -ne 0) { throw 'Flutter依赖安装失败。' }
    & $fitnessFlutter run -d $fitnessDevice --dart-define=API_BASE=http://127.0.0.1:8000
    if ($LASTEXITCODE -ne 0) { throw 'Android构建或运行失败，请查看上方具体错误。' }
} finally {
    Pop-Location
    $env:JAVA_TOOL_OPTIONS = $fitnessPreviousJavaOptions
}
