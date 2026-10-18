# LiftLab · AI 健身 App

第一阶段可运行工程：Flutter 客户端、FastAPI API、浏览器预览。聚焦平板杠铃卧推、高杠深蹲、传统硬拉；自重训练预留为独立模块。

## 当前能力

- 本机单用户画像保存，成年用户校验。
- 三大项起始模板、营养目标估算、计划版本与画像快照。
- 重量、组次、RPE、不适记录；不适时不建议自动加重。
- 示例食物库、按克数计算营养、记录与删除。
- 当天饮食按早餐/午餐/晚餐/加餐汇总，显示热量、蛋白质、脂肪、碳水的摄入与计划目标、差额及进度。北京时间划分日期，历史记录不进入当天汇总；画像变化后提醒更新目标。
- 餐食照片与训练录像上传、文件大小限制、拍摄指引。
- 实时训练：三大项取景框、机位指引、耳机测试、本地姿态帧流、实验性计次与语音播报（Android/iOS待真机验证）。
- SQLite 持久化，文件保存在 `data/uploads`。

**尚未接入：** 餐食视觉识别、杠铃追踪、经过验证的动作纠错、大模型、登录、周度调整、食谱推荐、专业内容审核。旧录像上传仍返回 `awaiting_integration`；实时训练另走本地姿态处理。计划为起始规则模板，经验字段目前只保存，尚未用于分层；营养使用固定活动系数1.4。示例食物数据仅用于开发验证。

## 启动后端与浏览器预览

需要 Python 3.10+（本项目已建立 `.venv`）。

```powershell
cd D:\ai-train
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.lock.txt
.\start.ps1
```

打开 http://127.0.0.1:8000；接口文档 http://127.0.0.1:8000/docs。

`start.ps1` 默认独立后台运行，关闭终端后服务仍可使用；日志在 `data/logs`。需要前台查看日志时使用 `./start.ps1 -Foreground`（先停止已有后台服务）。电脑重启后重新执行启动脚本。预览地址应在运行项目的同一台电脑上打开。

```powershell
.\.venv\Scripts\python.exe -m pytest backend -q
```

## Flutter 客户端

Flutter SDK 安装在 `.tools/flutter`，不提交进版本控制。

```powershell
cd D:\ai-train\mobile
..\.tools\flutter\bin\flutter.bat pub get
..\.tools\flutter\bin\flutter.bat run -d chrome
```

构建并由后端提供 Flutter Web：

```powershell
..\.tools\flutter\bin\flutter.bat build web --release --base-href /app/
```

构建后重启后端，打开 http://127.0.0.1:8000/app/。根路径仍是轻量浏览器预览。

Android 模拟器使用 `--dart-define=API_BASE=http://10.0.2.2:8000`。真机需要局域网地址和后端局域网监听；当前后端没有登录鉴权，只适合可信本机开发。iOS 构建需要 macOS、Xcode。Android 构建需要 Android SDK。

当前 Android Debug 仅允许 localhost、127.0.0.1、10.0.2.2 的明文开发连接；其他设备地址及发布版本应使用 HTTPS。实时训练入口会请求相机权限，音频采集关闭；只预览和本地检测，不录制视频。见 `docs/REALTIME_COACHING.md`。

## 结构

```text
backend/       API、规则、SQLite、回归测试
mobile/        Flutter 原生移动端与 Web 客户端
preview/       不依赖 Flutter 的浏览器业务预览
docs/          后续任务与模型接入约定
data/          本机数据（不提交）
```

## 下一步

见 `docs/ROADMAP.md`。上线前替换为经过审核的规则与授权食物数据库，完成用户鉴权和数据隔离、真实媒体格式校验、存储删除策略及 AI 评测。当前上传按 MIME 和大小校验，尚不解码验证真实媒体内容。
