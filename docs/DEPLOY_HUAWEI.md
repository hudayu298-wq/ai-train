# 华为云后端部署（Ubuntu 24.04）

## 账号版本说明

本项目已增加 PostgreSQL、多用户鉴权与微信 OAuth；当前账号版本的配置、安装前置条件和验收以 [登录配置](LOGIN_SETUP.md) 为准。下方 SQLite 路径与迁移内容保留供旧版本备份恢复参考，不代表账号版本仍使用 SQLite。

## 初始部署与历史版本范围

部署方式为 Python 虚拟环境 + Uvicorn + systemd，数据库继续使用现有 SQLite，适合个人开发测试。
这不是多租户版本；当前业务接口没有登录和用户隔离。安装器默认仅监听 `127.0.0.1:8000`。
本文提供部署步骤；实际是否部署成功，以服务器上的服务状态和数据库校验结果为准。

| 内容 | 服务器位置 |
|---|---|
| 当前代码与独立 Python 环境 | `/opt/liftlab/current` |
| 历史代码版本 | `/opt/liftlab/releases/` |
| 持久数据库 | `/var/lib/liftlab/fitness.db` |
| 上传文件 | `/var/lib/liftlab/uploads/` |
| 模型配置 | `/etc/liftlab/liftlab.env`，仅 root 可读 |
| 每日备份 | `/var/backups/liftlab/`，最近 7 份 |

代码更新使用新版本目录，不覆盖数据库目录。新部署自动初始化食物库、动作库和其他系统数据。
本机个人记录不是代码包的一部分；需要迁移时先对本机 SQLite 做一致性备份，再单独迁移。

## 连接服务器

提供公网 IP、SSH 用户名和端口。密码通过本机交互输入，私钥保留在本机。
使用本机密钥示例：

```powershell
ssh -i C:\path\to\server.pem -p 22 root@SERVER_IP
```

第一次连接会核验主机密钥。遇到已知主机密钥不一致应先核实，不关闭校验。
如果连接在 `kex_exchange_identification` 阶段被关闭，此时尚未验证登录密码；先使用华为云控制台远程登录检查 SSH 服务和服务器访问限制。

## 打包与安装

在项目根目录执行：

```powershell
.venv\Scripts\python.exe scripts\package_backend.py
```

生成 `.tools/deployments/latest/package.json` 和带校验和的版本压缩包。
包中包含后端源代码、模型提示词、食物/动作种子、示例图片和 Linux 服务文件。
包中不含 `.env`、本机 SQLite、上传记录、GitHub 凭据、手机 SDK 或构建缓存。

通过 SSH 创建仅本人可读的临时目录，并用 SCP 上传压缩包；核对服务器端 `sha256sum` 与 `package.json` 的 `sha256` 一致。
解压到新的临时目录，然后以 root 执行：

```bash
apt-get update
apt-get install -y python3 python3-venv ca-certificates
bash /PATH/TO/EXTRACTED/deploy/linux/install.sh /PATH/TO/EXTRACTED RELEASE_ID
```

`RELEASE_ID` 使用 `package.json` 中的 `release` 值。重复部署须新建版本包；已有版本目录不会覆盖。
安装器使用锁定依赖；新版本健康检查失败会尝试切回旧代码版本，数据库保留部署前备份，不自动覆盖业务数据。
备份包含一致性 SQLite 快照及上传文件；每日北京时间 03:30 左右执行，部署成功后也立即备份。
备份与数据在同一台服务器上，不能代替异地备份；正式使用时应另配私有对象存储备份。

## 验证和临时访问

```bash
systemctl status liftlab --no-pager
systemctl list-timers liftlab-backup.timer --no-pager
curl --fail http://127.0.0.1:8000/api/health
curl --fail 'http://127.0.0.1:8000/api/catalog?extended=true'
journalctl -u liftlab -n 80 --no-pager
```

从电脑建立 SSH 隧道，使用不与本机开发服务冲突的端口：

```powershell
ssh -N -L 127.0.0.1:18000:127.0.0.1:8000 root@SERVER_IP
```

之后电脑访问 `http://127.0.0.1:18000/docs`。关闭这条连接即关闭临时隧道。
当前手机 APK 仍指向原有地址，服务器部署不会自动改变已安装 APK 的接口地址。
手机脱离电脑使用需要配置 HTTPS、访问控制以及 App 的线上接口地址。

## AI 与数据库维护

在服务器用 `sudoedit /etc/liftlab/liftlab.env` 填入所选服务的 `AI_API_KEY`、`AI_BASE_URL` 和 `AI_MODEL`；视觉模型按需填写 `VISION_*`。
保存后运行 `systemctl restart liftlab`。密钥不提交 Git，也不放入 App 或截图。
模型未配置时普通记录、资料库等接口仍可使用，AI 生成接口返回明确的未配置提示。

手动备份：

```bash
systemctl start liftlab-backup.service
journalctl -u liftlab-backup -n 20 --no-pager
```

恢复备份时先停止服务、保留现有数据库和上传目录，在独立目录验证备份完整性，再替换业务数据并恢复属主权限。
不要直接覆盖运行中的 SQLite，也不要将数据库端口或无鉴权业务接口开放到公网。
