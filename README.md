# 练伴 · AI 健身 App

第一阶段可运行工程：Flutter 客户端、FastAPI API、浏览器预览。聚焦平板杠铃卧推、高杠深蹲、传统硬拉；自重训练预留为独立模块。

当前架构、AI调用链与提示词、配置状态及验收缺口见 [架构与AI说明](docs/ARCHITECTURE_AND_AI.md)。

## 当前能力

- 4 位 Q 版人类健身教练，可拖动、点击互动、收起；独立性格提示词用于对话，离线提醒按性格区分。入口为主页右上角“切换桌宠教练”，见 `docs/COACH_PERSONAS.md`。界面采用黑白灰与蓝色，见 `docs/UI_REDESIGN.md`。
- 虚拟教练形象与昵称、训练日/时间/提前准备提醒、三餐提醒；Android/iOS 使用本地系统通知，Web 使用前台提示。设置入口“我→私教提醒”，说明见 `docs/COACH_REMINDERS.md`。Android 锁屏实际送达仍需新版安装后真机验证。
- 首页为 AI 私教对话；首次进入自动引导配置画像并生成待确认计划。侧边栏进入饮食、训练计划、训练记录与复盘、AI 陪训和“我”。对话可提取并记录带用户原文依据的画像；提示词与接入见 `docs/AI_COACH.md`。
- 邮箱注册/登录/密码恢复、安卓微信 OAuth 接入、设备会话管理和账号注销；画像、聊天、饮食与训练按用户隔离。微信与 SMTP 需外部配置，见 [登录配置](docs/LOGIN_SETUP.md)。
- 根据每周训练日、单次时长、目标、力量和恢复生成整体周期计划，确认启用后可修改。RM在“我”中维护；训练后AI结合确认记录评估下一次重量或次数，展示变化和原因并支持撤销。缺少可靠RM时重量待确认，历史伤病只作风险及选动作上下文。模型配置与进阶范围见 `docs/AI_PLANS.md`。
- 重量、组次、RPE、不适记录；不适时不建议自动加重。
- 关节动作分类、训练部位标签、38张原创示意GIF、结构化动作细节与AI观察共用提示资料（`docs/MOVEMENT_CONTENT.md`）；视觉服务需单独配置，未进行真实模型准确率验证。
- 食物库与动作库：搜索、分类、导出；管理员可新增、编辑、停用及导入。初始44条食物、38个动作，数据来源见 `docs/LIBRARIES.md`。
- 当天饮食按早餐/午餐/晚餐/加餐汇总，显示摄入与画像估算营养目标、差额及进度；目标独立于训练计划，画像变化后自动更新。
- 餐食照片与训练录像上传、文件大小限制、拍摄指引。
- 实时训练：三大项取景框、机位指引、耳机测试、本地姿态帧流、实验性计次与语音播报（Android相机与语音已验证，计次待训练验证；iOS待真机验证）。
- 云端 PostgreSQL / SQLAlchemy / Alembic；本地默认使用独立 `data/fitness-v2.db` 开发库，不读取旧单用户记录。私人媒体下载需要鉴权。

**尚未接入：** 餐食视觉识别、杠铃追踪、经过验证的动作纠错、食谱推荐、专业内容审核。AI计划与训练后进阶接口已实现，真实生成需配置API密钥与模型。当前自动进阶只调整重量或次数，不自动修改组数和休息；新周期需用户生成并确认。旧录像上传仍返回 `awaiting_integration`；实时训练另走本地姿态处理。RM评估是参考规则，营养使用固定活动系数1.4。USDA食物条目保留来源与生熟状态，原4条示例标记未核验。

## 启动后端与浏览器预览

需要 Python 3.10+（本项目已建立 `.venv`）。

```powershell
cd D:\ai-train
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.lock.txt
.\start.ps1
```

打开 http://127.0.0.1:8000；接口文档 http://127.0.0.1:8000/docs。

`start.ps1` 默认独立后台运行，关闭终端后服务仍可使用；日志在 `data/logs`。需要前台查看日志时使用 `./start.ps1 -Foreground`（先停止已有后台服务）。电脑重启后重新执行启动脚本。预览地址应在运行项目的同一台电脑上打开。首次账号可按登录配置使用终端交互创建；没有配置邮件和微信时，不提供假验证码或匿名入口。

```powershell
.\.venv\Scripts\python.exe -m pytest backend -q
```

## 云服务器部署

华为云 Ubuntu 24.04 的后端部署、systemd 自启与每日备份见 [部署说明](docs/DEPLOY_HUAWEI.md)；PostgreSQL、登录和微信/邮件配置以 [登录配置](docs/LOGIN_SETUP.md) 为准。默认仅监听本机，完成 HTTPS 后再配置手机线上地址。

## Flutter 客户端

Android USB真机调试见 `docs/ANDROID_DEBUG.md`；SDK安装与手机授权完成后，在项目根目录运行 `./debug-android.ps1`。

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

构建后重启后端，打开 http://127.0.0.1:8000/app/。根路径重定向至登录后的 Flutter 客户端；旧轻量预览不再作为业务入口。

Android 模拟器使用 `--dart-define=API_BASE=http://10.0.2.2:8000`。真机需要局域网地址和后端局域网监听；当前接口需要登录；明文地址仅用于本机开发，线上使用 HTTPS。iOS 构建需要 macOS、Xcode。Android 构建需要 Android SDK。

当前 Android Debug 仅允许 localhost、127.0.0.1、10.0.2.2 的明文开发连接；其他设备地址及发布版本应使用 HTTPS。实时训练入口会请求相机权限，音频采集关闭；只预览和本地检测，不录制视频。见 `docs/REALTIME_COACHING.md`。

## 结构

```text
backend/       API、规则、账号、SQLAlchemy、回归测试
mobile/        Flutter 原生移动端与 Web 客户端
preview/       旧浏览器原型资源（当前业务入口为Flutter）
docs/          后续任务与模型接入约定
data/          本机数据（不提交）
```

## 下一步

见 `docs/ROADMAP.md`。上线前替换为经过审核的规则与授权食物数据库，验证真实微信/邮件和公开服务配置、真实媒体格式校验、存储删除策略及 AI 评测。当前上传按 MIME 和大小校验，尚不解码验证真实媒体内容。

### 训练经历与复盘

侧边栏“训练记录与复盘”可记录整次训练的每组重量、次数、RPE、不适和感受，完成后保存基础复盘、生成AI建议并评估计划进阶。实时陪训支持多组暂存和整次确认。确认记录沉淀到“我 → 训练档案”，供后续对话和计划参考。详见 [训练档案说明](docs/TRAINING_MEMORY.md)。
