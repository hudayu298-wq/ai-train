# 练伴 · AI私教 App

当前工作区：后端 **0.5.1** / Flutter **0.5.1+8**。资料核对：2026-11-02。

## 新窗口开发从这里开始

在同一目录`D:\ai-train`打开Local会话。**当前存在大量未提交代码和未跟踪文件，main分支不能代表最新工程；不要重新拉main覆盖本地，也不要清理工作区。**

建议阅读顺序：

1. [开发接手规则](AGENTS.md)
2. [PRD：产品需求与验收](docs/PRD.md)
3. [当前架构与AI交互](docs/ARCHITECTURE_AND_AI.md)
4. [开发状态、验收证据与下一步](docs/DEV_STATUS.md)
5. [新会话交接：环境、命令和可复制开场信息](docs/DEVELOPMENT_HANDOFF.md)
6. [专项文档索引](docs/INDEX.md)

旧资料保留为历史参考，不能与当前状态混读。本地代码、云端服务、手机APK、已激活知识版本是不同交付物：**云端为0.4.0基线，已单独更新6位密码规则、1579条动作目录与302套演示；完整本地0.5.1未部署到云端；本地V2已于2026-10-28通过两层评测并激活，115节点/22来源/291关系，保留V1回滚；本轮未更改云端。**

## 当前工程能力

- 对话式私教Agent：四位Q版人类教练、画像提取、真实业务工具、待确认操作、执行记录、幂等与恢复、来源引用。
- 问题按健康恢复、训练计划、饮食、实际训练、知识研究及画像分流，支持多领域及追问；规则→Jev/OpenAI原生决策（需专用密钥）或本地语义→专项harness。当前本机使用本地层，见[分层路由](docs/AGENT_ROUTING.md)。
- 画像必填胸/背/腿各一项熟悉动作的实际力量表现，支持变式；生成有具体建议重量、来源及首训校准提示的AI周期草稿，用户确认及编辑。RM独立可选，训练记录与复盘独立；训练后受限进阶显示差异、可撤销，整周达标后评估可推进，手动周期操作另行确认。见[力量画像](docs/STRENGTH_PROFILE.md)。
- 当天饮食按餐汇总热量和宏量，与可设置、可追溯的营养目标对比；授权数据满足条件后提出确认式趋势校准。
- 底层动作库1579条，本地默认精简为97个经典/常用动作；32类关节/功能标签和训练部位联动；素材共302套许可三帧演示。保留原38条动作身份，47条含糊分类待复核；食物库44条。
- 健康数据手动/文件导入、独立AI授权；手动膝触墙cm协议、基线与趋势。没有设备厂商自动同步或摄像头自动测角。
- 三大项端侧实验性姿态/计次/语音、机位和取景框；截图视觉分析需独立服务配置和准确率验证。
- 审核论文、版本化基础知识、实际检索工具、混合检索与评测/发布/回滚；知识或表达策略的自动改进仅产生候选。
- 登录/多用户隔离、管理员权限、设备会话、注销、本地通知；SMTP和微信仍需外部配置与真实联调。
- Redis 缓存提示词、画像事实、训练记忆与公开知识检索，按用户隔离、数据更新后失效，故障回到原数据源；本地已启用，见[缓存运行说明](docs/REDIS_CACHE.md)。
- 来源删除、更正或撤回授权后，清理旧AI回复/快照并阻止处理中任务回灌，保留确认目标与独立事实；见[隐私生命周期](docs/PRIVACY_LIFECYCLE.md)。隔离PG验收可用[专用脚本](docs/POSTGRES_ACCEPTANCE.md)重建，不连接业务库运行测试。

**未达到发布或能力声明条件：** 本地V2已过既有发布门槛，云端推理容量、独立专家盲测与并发资源仍待验收；未证明全球SOTA。餐食图片营养识别、经过验证的动作纠错、完整解剖图谱、设备自动同步、正式公网服务等仍有缺口。新增动作/动图不会自动开启实时检测。详细能力状态与PRD验收条件分开记录。

## 本地启动

需要Python环境`.venv`；Flutter SDK位于`.tools/flutter`。凭据、真实数据、模型/SDK和APK不进入Git，换机器需自行配置。

```powershell
Set-Location D:\ai-train
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.lock.txt
.\start.ps1
```

打开[Flutter预览](http://127.0.0.1:8000/app/)。`start.ps1`默认后台启动；已有服务时不会热重载代码。日志位于`data/logs`。缺账号时参照[登录配置](docs/LOGIN_SETUP.md)使用交互工具，不通过聊天发送密码。

本机 Redis 已配置为随 `start.ps1` 启动；新机器可运行 `.\.venv\Scripts\python.exe scripts/setup_redis.py` 安装项目内 Windows 社区开发构建，或使用 `deploy/redis.compose.yaml` 的官方 Linux 镜像。未配置 Redis 时仍可启动。状态检查：`.\.venv\Scripts\python.exe scripts/cache_status.py`；安装来源、停用和生产配置见[REDIS_CACHE](docs/REDIS_CACHE.md)。

Flutter验证和Web构建：

```powershell
Set-Location D:\ai-train\mobile
..\.tools\flutter\bin\flutter.bat analyze --no-pub
..\.tools\flutter\bin\flutter.bat test --no-pub
..\.tools\flutter\bin\flutter.bat build web --release --base-href /app/ --no-pub
```

后端测试应在独立终端、隔离数据库运行；fixture会删除测试账号和目录。先读[安全的测试命令](docs/DEVELOPMENT_HANDOFF.md)，不要指向正式数据库。

## 工程结构

```text
backend/       FastAPI模块化单体、账号、SQLAlchemy、业务服务、Agent和测试
backend/data/  目录seed、固定知识版本、评测数据和模型清单
backend/assets/公开许可素材；与用户私人上传分开
mobile/        Flutter Android / Web业务界面与端侧姿态、语音、通知
scripts/       构建、导入、备份、账号和有界worker脚本
deploy/linux/  systemd、部署、备份、私有测试入口
docs/          当前需求、架构、状态、交接与专题；history保存历史版本
preview/       旧原型资源；业务入口为Flutter Web
data/          本机私有运行数据（忽略）
.tools/        本机SDK/模型/构建与验收产物（忽略）
```

## 部署和手机

生产使用PostgreSQL及显式Alembic迁移；本地默认SQLite。后端与数据库loopback监听，手机通过Tailscale私有HTTPS测试；域名正式入口尚未完成验收。后端包、Web产物、APK及知识激活需要分别验证。

最近APK：`.tools/apks/lianban-private-test-0.5.1-arm64.apk`，仅保存到电脑。其接口指向云端，**云端未同步时手机仍显示旧库**。最新版本、签名、测试与部署记录以[开发状态](docs/DEV_STATUS.md)为准。

接下来先看[工作队列](docs/ROADMAP.md)，不要按旧路线图重新实现已经存在的功能。
