# 新会话开发交接

更新时间：2026-10-30。目标是无需依赖旧聊天全文，在同一工作区继续开发。

## 1. 应怎样打开新窗口

在Codex中为现有项目`D:\ai-train`打开一个 **Local** 会话，并停止旧窗口的并发代码修改。无需新建仓库或重新拉取main。当前大量功能为未提交文件，直接从main创建新worktree/clone会缺失它们。

先读根目录`AGENTS.md`，再读README、PRD、架构、DEV_STATUS。专项文档按任务查[INDEX.md](INDEX.md)。旧窗口上下文不是必要输入，磁盘文件和开发状态是交接依据。

```powershell
Set-Location D:\ai-train
git status --short
git branch --show-current
git log -1 --oneline
```

发现工作区与DEV_STATUS不一致，先核实新变化，不清理或覆盖现有文件。`.tools`、本地数据、模型、SDK、凭据和APK是机器环境，不会随Git克隆自动出现。

## 2. 环境与入口

| 项目 | 位置/说明 |
|---|---|
| Python | `.venv\Scripts\python.exe`；依赖锁`backend/requirements.lock.txt` |
| Flutter/Dart | `.tools\flutter\bin\flutter.bat`、`dart.bat` |
| Java | `C:\Program Files\Java\jdk-17` |
| Android SDK | `.tools\android-sdk` |
| 本地配置/数据 | `.env`、`data/fitness-v2.db`、`data/uploads`；不提交或打印敏感内容 |
| 本地预览 | `http://127.0.0.1:8000/app/` |
| 签名 | `mobile/android/key.properties`与本地受保护keystore；保持现有签名，不生成替代证书 |
| 当前Android身份 | 包名`com.liftlab.liftlab`；MD5`EE473B11FBF59CC96EB26CF91334DC92` |
| 本地神经模型 | `.tools/retrieval-models`；清单`backend/data/knowledge_models_manifest.json` |
| 本地 Redis | 项目内社区 Windows 开发构建 8.10.3，`127.0.0.1:6379`，64MB 无持久化；`data/redis-cache.json` 自动启动配置，见 [REDIS_CACHE](REDIS_CACHE.md) |

Python依赖安装和启动：

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.lock.txt
.\start.ps1
```

`start.ps1`在已有listener时不会自动重载Python代码。需重启时，先验证8000端口进程确为本工作区Uvicorn，再重启；不要杀其他服务。日志在`data/logs`。本地账号如需创建，按LOGIN_SETUP用交互密码工具，不复制云端账号或向聊天索要口令。

`start.ps1` 会尝试启动已配置的本地 Redis；失败会回到数据库/文件。新机器可用 `scripts/setup_redis.py` 安装已锁定摘要的项目内开发构建，或使用官方 `deploy/redis.compose.yaml`（本机没有 Docker，未执行）。检查可用性用 `.\.venv\Scripts\python.exe scripts/cache_status.py`，关闭缓存设置 `REDIS_CACHE_ENABLED=false`；不要打印连接 URL。缓存加速不改变知识发布门槛，后续评测必须绑定当前源码。

主聊天新增 [AGENT_ROUTING](AGENT_ROUTING.md) 领域漏斗，状态脚本 `.\.venv\Scripts\python.exe scripts/agent_router_status.py`。当前未配置Jev/OpenAI专用密钥，实际为规则+本地语义+领域harness；原生System One/Decisions适配已做隔离HTTP测试，真实可用性另需配置与实调。不要把原AI_API_KEY发送给别家或把密钥发到聊天。路由策略/harness变更后旧未完成任务需重新提问，原待确认操作及已保存事实沿原业务校验处理。

## 3. 验证命令

### 后端：独立测试终端

测试fixture会删账号及公共测试表。**不要使用生产DATABASE_URL跑pytest。** 使用独立测试终端，下面显式空URL阻止`.env`把云端连接注入本次进程；不改真实`.env`文件。

```powershell
Set-Location D:\ai-train
$env:APP_ENV='test'
$env:DATABASE_URL=''
$env:KNOWLEDGE_RETRIEVAL_MODE='bm25'
.\.venv\Scripts\python.exe -m pytest backend tests -q --tb=short
```

测试自行创建临时SQLite，两项PostgreSQL专项跳过。PG验收必须使用下列脚本新建物理集群，不能手填现有业务URL；fixture在导入应用前检查显式test环境及随机库标记。普通BM25测试不证明ONNX推理或真实LLM质量。

```powershell
.\.venv\Scripts\python.exe scripts/run_postgres_acceptance.py --tests all
```

使用项目内固定版本PG16、独立owner/app角色、随机loopback端口，执行迁移/并发/权限/备份恢复并停止集群；详见[POSTGRES_ACCEPTANCE](POSTGRES_ACCEPTANCE.md)。删来源、撤权及迟到AI响应规则见[PRIVACY_LIFECYCLE](PRIVACY_LIFECYCLE.md)。不要为普通测试改真实`.env`或关闭隔离校验。

可选真实 Redis 集成验证：在上述隔离测试进程额外设置 `REDIS_URL=redis://127.0.0.1:6379/15`、唯一 `REDIS_CACHE_NAMESPACE`，运行 `backend/test_cache.py` 及业务专项。测试 transport 用例使用替身，其他业务用例可走真实 Redis；只清理本次 namespace 的 key，禁止 FLUSHALL/FLUSHDB。未配置 URL 的临时 FIT_DATA_DIR 不读取真实本机缓存配置。

普通业务测试fixture显式使用`AGENT_ROUTING_MODE=rules`，避免每个无关用例启动ONNX或访问决策服务。`backend/test_agent_routing.py`单独覆盖本地语义分支和Jev/OpenAI原生HTTP协议、拒答/低置信度/超时/预算、领域扩展及中断批次；本机真实ONNX和聊天模型烟雾回执另见DEV_STATUS，不把transport替身当外部模型真实验收。

只改某模块时优先运行相应测试，如`backend/test_strength_profile.py`、`test_external_exercises.py`、`test_periodization.py`、`test_nutrition_guidance.py`、`test_context_consent_audit.py`等，避免反复运行无关的付费评测。

2026-10-26力量画像增量见[STRENGTH_PROFILE](STRENGTH_PROFILE.md)。新生成计划要求胸背腿各一项实际表现，缺失不能调用模型；不能恢复旧版“无RM即清空重量”的规则。旧未启用草稿需重新生成，已保存计划/RM/训练不自动迁移。测试生成成功路径需显式准备三部位合成资料，不可在全局fixture自动补齐，缺失拦截用例仍须覆盖。

### Flutter

```powershell
Set-Location D:\ai-train\mobile
..\.tools\flutter\bin\flutter.bat analyze --no-pub
..\.tools\flutter\bin\flutter.bat test --no-pub
..\.tools\flutter\bin\flutter.bat build web --release --base-href /app/ --no-pub
```

缺依赖时先`flutter pub get`。Web产物位于`mobile/build/web`，由本地后端服务；后端tar包不带此产物。不要把Wasm兼容提示误当作JS Web构建失败，要看最终退出码和成功信息。

### 仅保存APK

```powershell
$env:JAVA_HOME='C:\Program Files\Java\jdk-17'
$env:ANDROID_HOME='D:\ai-train\.tools\android-sdk'
..\.tools\flutter\bin\flutter.bat build apk --release --target-platform android-arm64 --dart-define=API_BASE=https://lianban-test.tail33f536.ts.net --no-pub
```

在mobile目录执行。产物为`build/app/outputs/flutter-apk/app-release.apk`，用apksigner核对签名、aapt核对版本/包名，再保存到`.tools/apks`。当前用户偏好仅保存，不自动安装手机。APK中的API地址指向云端，本地有新库不代表这个包连接到的云端也有新库。

## 4. 资料/模型的重建

- 完整目录：`python scripts/import_exercise_catalog.py`；已固定来源提交、许可与SHA，首次下载906帧。`--skip-media`只重建数据。
- 重建seed不自动覆盖已入库目录；需要更正目录时显式比较并迁移仅由导入器维护的未编辑条目，保持用户编辑、归档和旧训练快照。先看EXERCISE_CATALOG_IMPORT。
- 模型素材：`python scripts/download_retrieval_models.py --directory .tools/retrieval-models`；不能为了加载成功跳过SHA验证。镜像仅作传输，仍核对固定上游哈希。
- 真实检索/QA评测：按KNOWLEDGE_RETRIEVAL_EVALUATION执行，使用隔离数据、明确实际模型和预算，保存全量报告。旧失败结果、旧28问成绩或BM25降级不能作为v2通过证明。

## 5. 云端接手

最后有回执的主机为华为云Ubuntu24.04，公网IP`113.45.193.50`，SSH root/22；这是历史运维入口，不表示本次已重新连通。私钥只使用本机已配置的`~/.ssh/liftlab_huawei_ed25519`路径，不查看/输出内容。不要把机器密钥复制进Git或新文档。

- 当前链接：`/opt/liftlab/current`；发布目录`/opt/liftlab/releases`；业务数据`/var/lib/liftlab`。
- 运行env`/etc/liftlab/liftlab.env`，迁移owner env`/etc/liftlab/migration.env`，通过受控子进程加载，不打印。
- API与PG仅loopback。私有入口`https://lianban-test.tail33f536.ts.net`；Tailscale保持userspace，不能用内核TUN覆盖现有云DNS路径。
- 开始前只读核对服务版本/迁移版本、模型完整性和资源，不重置密码、画像、数据库或tailnet。
- 本地V2已于2026-10-28通过真实两层评测并激活；云端仍需单独部署/资源和PG验收并核对发布绑定，不能把本地激活当作云端已更新。V1冻结包仍为回滚基线。
- `scripts/package_backend.py`排除凭据/真实记录/SDK，但不含Flutter Web。源码SHA、脏工作区manifest和数据迁移都要有回执。
- `.tools/knowledge/release/staging.json`记录了最后旧发布；`.tools/sota`与`.tools/exercise-import`只是本机中间产物，不能直接当新部署成功。

## 6. 可直接粘贴到新会话的开场信息

> 在D:\ai-train的当前Local工作区继续练伴开发。请先读AGENTS.md、README.md、docs/PRD.md、docs/ARCHITECTURE_AND_AI.md、docs/DEV_STATUS.md和docs/DEVELOPMENT_HANDOFF.md，再核对git status。当前代码0.5.1、动作库1579条/302套演示；最后确认云端仍0.4.0，本地V2已于2026-10-28通过原两层评测并激活，保留V1回滚；云端未在该轮更新。大量代码未提交，不要从main重建或清理文件。请按我接下来指定的任务继续；若只说“继续”，先给出DEV_STATUS中P0任务的具体待办和已有证据，再推进可独立完成的工作。凭据不输出，APK默认只保存，不自动安装。

上述文字提供上下文，不代表自动授权推送、云端发布或跨会话发消息；后续具体动作仍依据用户指令及已有授权。
