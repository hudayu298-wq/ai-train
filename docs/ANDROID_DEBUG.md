# Android USB真机调试

本项目的Flutter位于 `.tools/flutter`，本地Android SDK安装路径为 `.tools/android-sdk`，启动脚本会自动检测此路径。Android项目最低系统API 24（Android 7.0），编译SDK 36，NDK 28.2.13676358。

## 首次准备

1. 安装官方Android Studio：https://developer.android.com/studio 。
2. More Actions → SDK Manager：安装Android SDK Platform 36、SDK Build-Tools、Platform-Tools、Command-line Tools (latest)、NDK 28.2.13676358。首次构建可能继续下载Gradle与原生依赖。
3. 在PowerShell中配置SDK并自行阅读确认许可：

```powershell
cd D:\ai-train
.\.tools\flutter\bin\flutter.bat config --android-sdk "$env:LOCALAPPDATA\Android\Sdk"
.\.tools\flutter\bin\flutter.bat doctor --android-licenses
.\.tools\flutter\bin\flutter.bat doctor -v
```

如果SDK安装在其他位置，将路径替换为实际目录。Visual Studio警告不影响Android调试。

4. 手机：设置 → 关于手机 → 连续点击版本号打开开发者选项；进入开发者选项开启USB调试。不同品牌入口名称可能不同。
5. 用支持数据传输的USB线连接，解锁手机并确认允许这台电脑调试。如设备无法识别，检查数据线、USB模式和厂商Windows驱动。

荣耀手机：同时开启“USB调试”和“仅充电模式下允许ADB调试”。如果Windows已有“ADB Interface”但ADB设备列表仍为空，检查是否使用通用WinUSB驱动；本机通过安装荣耀官方手机助理，恢复了Android Composite ADB Interface驱动并成功识别Magic7 Pro（Android 16）。安装程序的管理员授权和厂商协议需在电脑上确认。

若环境设置了匿名HTTP格式的 `HTTPS_PROXY`，调试脚本会临时为Gradle设置代理，并在退出时恢复原来的Java选项。

荣耀系统可能将 `persist.log.tag` 设为 `S`，导致Flutter一直等待VM Service。脚本检测到此配置时，仅临时设置 `log.tag.flutter=I`，允许发现调试服务；手机重启后失效。

## 启动

```powershell
cd D:\ai-train
.\debug-android.ps1
```

自定义SDK路径或多个设备：

```powershell
.\debug-android.ps1 -SdkPath 'D:\Android\Sdk' -DeviceId '替换为设备序列号'
```

脚本启动本机后端，通过ADB reverse把手机8000端口映射到电脑8000端口，然后构建安装调试版。此方式不要求手机和电脑同一Wi-Fi；USB连接需保持。重新连接后重新运行脚本建立端口转发。

运行后按r热重载，按R热重启，按q结束调试。原生依赖或权限配置变化需重新构建安装。

## 优先验证

本机已成功构建调试APK：`mobile/build/app/outputs/flutter-apk/app-debug.apk`。若安装返回 `INSTALL_FAILED_ABORTED: User rejected permissions`，保持手机解锁，在手机确认USB安装提示；如系统提供“USB安装”开关，检查该开关。允许后重新运行调试脚本。

真机验证：已在荣耀Magic7 Pro上安装并启动调试版，连接Dart VM Service，热重载成功；画像、计划、训练记录、RM和当天饮食的首次加载均返回HTTP 200。实时相机和耳机语音需要在手机上继续实际验证。

项目已关闭Kotlin增量编译，以避免Windows上项目与Pub缓存分别位于D盘和C盘时的跨盘缓存错误。

- 画像、用户计划、RM数据和当天饮食是否正常读写。
- 动作 → 进入实时训练 → 开启相机，确认系统相机权限。
- 按侧面框摆位，测试关键部位入框、实验性计次、耳机语音和后台恢复。
- 餐食照片识别及具体姿态纠错目前尚未完成，不把上传成功当作识别成功。

App数据目前保存在电脑后端；电脑关机或USB转发断开会影响业务接口。

参考： https://docs.flutter.dev/platform-integration/android/setup ， https://developer.android.com/studio/run/device 。
