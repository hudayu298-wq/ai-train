# Redis 缓存（本地 2026-10-29）

Redis 用于减少重复加载、训练历史汇总和神经检索，SQL/本地提示词文件仍是数据依据。当前已在本地接入；云端未部署。它不会缓存模型的最终回复，首次检索和外部模型生成仍需计算/请求。

| 内容 | 缓存位置与有效期 | 更新依据 |
|---|---|---|
| 计划、Agent、复盘、进阶提示词 | 进程内 L1；Redis 3600 秒 | 文件 stat 变化重读；内容 SHA256 绑定 Redis key，命中也校验正文摘要 |
| 画像已确认事实、确认训练形成的动态记忆 | Redis 120 秒，事务内副本 | owner、数据库、SQL 版本 nonce、参数绑定；训练记忆另绑定当天日期 |
| 公开知识检索结果及引用 | Redis 600 秒 | 当前知识包、撤回项、检索管线指纹、模式、查询及过滤参数绑定 |

原本在进程启动时加载的共同教练提示词/性格仍按原方式驻内存。健康/活动度原始数据、完整 Agent 上下文、授权结果、登录会话和最终 AI 回复不写入该缓存；健康/活动度授权和上下文修订仍即时检查。Redis 不作为任务队列或向量数据库。

## 本机运行

本机没有 Docker/可用 WSL，采用项目目录内的 [Redis Windows 社区开发构建 8.10.3](https://github.com/redis-windows/redis-windows/releases/tag/8.10.3)，不是 Redis 官方原生 Windows 发行版。安装器只下载到被忽略的 `.tools/redis` 并校验固定 SHA256，不创建系统服务，不改系统设置或 `.env`：

```powershell
.\.venv\Scripts\python.exe scripts/setup_redis.py
.\start.ps1
.\.venv\Scripts\python.exe scripts/cache_status.py
```

已配置的机器无需重复安装。安装器拒绝覆盖已有 `data/redis-cache.json`。`start.ps1` 调用 `scripts/start_redis.ps1`，验证可执行文件路径和摘要后隐藏启动；已有 6379 listener 必须属于同一项目二进制，其他服务不会被停止。Redis 启动失败时后端继续使用原数据源。

监听仅 `127.0.0.1:6379`，protected-mode 开启，64 MB、allkeys-lru、关闭 RDB/AOF，缓存随时可重建。运行文件在 `data/redis`，日志在 `data/logs/redis.*.log`。缓存没有持久化，不要把业务数据保存到该实例。

配置优先级：非空 `REDIS_URL` > `FIT_DATA_DIR/redis-cache.json`（默认 `data/redis-cache.json`）。`REDIS_CACHE_ENABLED=false` 完全禁用读取/写入缓存；`REDIS_CACHE_NAMESPACE` 可隔离多个应用/测试。远程连接要求 `rediss://` TLS；同机 loopback 与容器内部名 `redis` 允许 `redis://`。连接 URL、口令不可提交 Git 或输出日志。管理员 `GET /api/cache/status` 与本机状态脚本仅返回可用性和当前进程计数，不暴露连接资料。

服务已有 8000 listener 时 `start.ps1` 不热重载 Python 改动。代码更新后需要先核实进程属于本工作区，再重启后端；Redis 无需随每次 Python 改动重启。

Linux/有 Docker 的环境可选择固定摘要的官方镜像：

```powershell
docker compose -f deploy/redis.compose.yaml up -d
# 独立后端进程配置 REDIS_URL=redis://127.0.0.1:6379/0
```

此文件只发布宿主机 loopback 端口。本轮未运行 Docker 或部署云端；生产应使用官方 Linux 镜像/受管服务，按部署环境配置身份验证、访问控制和 TLS，不把本机社区开发构建当作生产发行版。客户端和安全配置参见 [redis-py 官方文档](https://redis.io/docs/latest/develop/clients/redis-py/) 与 [Redis 安全文档](https://redis.io/docs/latest/operate/oss_and_stack/management/security/)。

## 一致性与隐私

- `Store.cached_user` 每次先查 SQL 账号 active 状态及缓存 nonce，缓存命中与事务内 memo 均不能绕过账号检查。key 使用 HMAC，包含数据库/owner/nonce/参数的摘要，不放原始 owner、查询或用户资料。
- 缓存正文使用 Fernet 认证加密；私有正文密钥还依赖 SQL 中的 nonce，Redis key 不包含这个原始值。技术记录为 `user_records(kind=cache_meta,id=redis_epoch)`，不混入用户记忆/导出/AI事实，不新增表或 Alembic 迁移。
- 画像/训练及相关设置修改在同一 SQL 事务中换 nonce，提交后按 owner 索引尽力 UNLINK。事务内修改只走数据源和副本，不发布未提交内容；回滚保留原版本。Agent checkpoint 等无关写入不使记忆缓存失效。
- Redis 断连时照常读写 SQL，恢复后旧 nonce 的内容不可命中。连接/读写 timeout 150ms，失败后熔断 5 秒，避免每个请求重复等待。缓存损坏或过大时回到数据源，禁止截断事实后假装完整。
- 注销先停用账号/删除在线记录，再尽力清除该 owner 缓存；active 检查和 SQL nonce 删除阻断旧数据读取。Redis 故障、索引淘汰或并发旧读可能留下不可再访问的密文，依靠最多 120 秒 TTL 回收，不承诺物理上瞬间删除所有密文。所有清理均限定 namespace/owner，不使用 FLUSHALL/FLUSHDB。
- 公开知识命中前照常查当前版本和撤回项。降级检索结果不缓存，显式指定 `mode` 的评测绕过 Redis；命中诊断区分 `cache_hit`、本次 `latency_ms` 与原检索 `origin_latency_ms`，不把缓存延迟冒充神经推理耗时。

## 验证与性能口径

真实 Redis DB15、临时 SQLite、合成 500 条训练记录：首次汇总 54.076ms，7 次缓存读取中位数 3.797ms。单条 V2 知识查询首次约 17.24 秒（含加载模型/建索引），模型已加载后的显式绕过缓存约 5.736 秒，Redis 命中约 11.924ms；结果正文和引用相同。它是本机单场景验证，不是整体聊天延迟、压力测试或发布质量评测。原始回执 `.tools/redis-cache/acceptance.json` 与合成脚本在本机保留。

验证覆盖密文/TTL、owner 隔离、提交失效/回滚、断连后继续写读与重连不返旧值、撤权/账号注销、知识撤回与版本绑定、提示词变更及损坏回退。测试数据库全部隔离，不使用真实用户画像。完整实际测试结果见 [DEV_STATUS](DEV_STATUS.md)。

本轮源码/检索管线指纹改变，旧知识评测只是原发布时的记录，不能绑定未来新发布。当前已激活 V2 不变；没有重新进行 80 问/46 题发布评测、知识激活或云端部署，单查询性能验证不替代这些门槛。
