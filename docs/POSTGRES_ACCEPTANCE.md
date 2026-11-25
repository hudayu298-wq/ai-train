# 隔离 PostgreSQL 验收

更新：2026-11-02。仅本机合成数据；当前业务数据库没有切换到 PG，也未部署云端。执行结果与原始报告位置见 [DEV_STATUS](DEV_STATUS.md)。

最终完整运行 `447a57ea162b4a8d96056f40ae81c16f`：**369项通过（414.50秒）**，全部7项迁移/权限/锁/恢复检查通过；集群已停、测试namespace已清理。报告保存在`.tools/postgres-acceptance/447a57ea162b4a8d96056f40ae81c16f/report.json`。之前的357通过/3失败与900秒超时报告保留，不计为通过。

## 可重建命令

```powershell
Set-Location D:\ai-train
.\.venv\Scripts\python.exe scripts/setup_postgres_audit.py
.\.venv\Scripts\python.exe scripts/run_postgres_acceptance.py --tests all
```

`--tests privacy` 仅跑账号、隐私生命周期及授权专项；`--tests none` 仅检查迁移/权限/备份。二者不能冒充全量通过。完整日志在 `.tools/postgres-acceptance/<随机ID>/`，目录被忽略且限制为当前 Windows 用户访问。报告只含计数、哈希、检查结论，日志会脱敏合成密码和token；不得将整个临时集群目录上传Git。

工具使用项目内 EDB PostgreSQL **16.15-5** Windows x64 二进制，不安装系统服务。来源为 [PostgreSQL Windows 下载页](https://www.postgresql.org/download/windows/) 链接的 [EDB 二进制](https://productsdl.enterprisedb.com/download-postgresql-binaries)；固定下载包 SHA256 `43bb45f173a6f08cf1d29a97a6d8deb119e8e8093a24c00d2d1001a0ccaa8281`。校验后仅解压 bin/lib/share，禁止 ZIP 路径越界。

## 隔离与覆盖

每次产生随机物理集群、随机非5432端口与数据库/角色。只监听 `127.0.0.1`，SCRAM认证。随机密码只用于子进程环境或内存，初始化密码文件随后删除。脚本不接收现有数据库URL，不加载真实 `.env`；测试使用独立数据目录与唯一 Redis DB15命名空间，结束只删除本次命名空间。正常和失败路径均尝试停止该集群，报告必须确认 `cluster_stopped=true`。

1. 用独立 schema owner 迁移到0001，写入合成旧账号/画像，再升级0003；旧行哈希保留，新增健康、研究及知识表，重复升级无变化。
2. 应用角色 `NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOREPLICATION`，只有业务表DML、schema USAGE和sequence权限；迁移表只读。实测不能建表、改表、读密码目录或修改迁移版本。
3. 使用应用角色跑 `backend tests` 全量pytest，包括原来只在 PG 执行的并发与多进程用例；只允许合成数据。真实模型使用替身，BM25用于普通业务测试，不是神经检索或付费模型验收。
4. `pg_dump/pg_restore` 恢复到另一个空库，核对每表行数、行哈希，以及列/类型/默认值、约束和索引的 schema 哈希；重新授权后验证应用角色写入（回滚探针）。
5. 调用项目 `scripts/backup_data.py` 的真实 PG 分支，核对数据库dump与合成媒体归档、恢复后哈希一致。备份使用users表EXCLUSIVE锁，阻止业务写入使用的SELECT FOR UPDATE，同时允许pg_dump读取；另以两个应用连接实测锁冲突。连接、取锁和dump均有超时，失败释放连接。只有显式 SQLite 备份用例清空 PG URL，不隐藏 PG 业务失败。
6. 恢复升级前0001备份并重新升级0003，证明备份恢复路径。含数据的迁移不强行 downgrade；这不是生产无损在线回退方案。

`deploy/linux/install.sh` 同步限制应用角色对 `alembic_version` 的写权限，尚未在云端执行。Owner隔离依赖应用层过滤和用户锁，本次没有启用或宣称 RLS。

## 破坏性 fixture 防护

`backend/test_support.py` 在应用导入前要求显式 `APP_ENV=test`、`DATABASE_URL` 存在。空 URL 才由 fixture 创建临时 SQLite；非空必须是本机随机测试库/角色、非5432端口，并验证脚本注入的数据库 nonce。缺失或不匹配时在清表前退出。禁止手工把真实业务 URL 填入 pytest。

```powershell
$env:APP_ENV='test'
$env:DATABASE_URL=''
$env:KNOWLEDGE_RETRIEVAL_MODE='bm25'
.\.venv\Scripts\python.exe -m pytest backend tests -q --tb=short
```

## 尚未覆盖

没有安装 pgvector；0003 的无 vector 扩展分支已覆盖，JSON/NumPy精确检索不是pgvector验收。Windows本机 PG16 不能代替云端 Linux 的版本、资源、模型内存、并发/P95、生产数据规模及恢复演练。真实 LLM、80问神经检索、46问知识发布、手机端到端与云端部署不在此任务的自动化结论内。没有迁移真实用户资料或重发V2知识。
