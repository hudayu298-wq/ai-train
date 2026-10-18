# 登录系统配置与验收

## 本次实际交付（2026-10-18）

- 华为云后端已切换到 PostgreSQL 16 和账号版本；API 仍只监听 `127.0.0.1:8000`，PostgreSQL 仅监听回环地址。
- 应用角色无建表权限；迁移角色独立保存。旧 SQLite 已备份保留，电脑个人数据未迁移。
- 真实 PostgreSQL 后端测试 75 项通过，涵盖并发刷新/微信登录、用户隔离、媒体与管理员权限。
- 云端实际服务的 401、用户隔离、重启持久化、退出撤销和备份恢复验收通过；临时账号已清除。
- Flutter 全套 28 项测试及 analyze 通过，安卓调试 APK 和 Web 已构建；SMTP SSL/STARTTLS 发送另有模拟测试通过。
- 微信 AppID/AppSecret、SMTP、最终域名与 HTTPS 尚未配置。真实微信和邮件送达未验收，APK 使用本地调试接口地址，未安装到手机。

后续更新：用户已注册 `lianbanfit.top`；2026-10-18 检查时根域名 A 记录已指向 `113.45.193.50`，`api.lianbanfit.top` 暂无解析。建议新增 `api` A 记录到同一服务器，再以该子域名作为接口入口。备案状态待确认。

用户暂时无法取得微信开放平台登录资质，当前以邮箱账号为登录方式。微信登录及绑定入口只在服务器报告 `wechat_enabled=true` 时显示，保留后续接入能力；第三方认证平台不能代替申请微信自身的相应权限。

服务器验收记录：`/var/lib/liftlab/accounts-verification.json`，不含凭据。

## 已实现的范围

- 邮箱验证注册、密码登录、找回/修改密码、绑定/更换邮箱。
- 微信开放平台移动应用 OAuth：安卓原生 SDK 拉起微信，服务器校验授权码后签发 LiftLab 会话。
- 访问令牌 15 分钟、刷新令牌轮换、设备退出、全部退出、会话撤销检查。
- 当前用户记录导出、账号注销、在线记录/媒体清除；注销后在途 AI 结果不能重新创建记录。
- PostgreSQL / SQLAlchemy / Alembic，用户范围的数据访问、系统库管理员权限、私有媒体下载。
- 数据库限流与单用户 AI 并发限制；验证邮件加密队列与定时发送。

动作分析和食物识别本身的模型能力不因登录改造而增加。

业务数据本期使用 `user_records(user_id, kind, id, payload JSONB)` 保留现有 API 结构；账号、身份、会话、验证、限流和系统库独立建表。饮食、计划、训练的进一步关系化拆表仍是后续工作，不能将本次改造描述为全部领域模型已拆分完成。

## 配置位置

电脑：项目根目录 `.env`。服务器：`/etc/liftlab/liftlab.env`，仅 root 可读。
迁移角色凭据仅在 `/etc/liftlab/migration.env`，不加载进运行中的 App 服务。
所有示例均不包含实际密钥。不要把密钥发到聊天或提交 Git。

```dotenv
APP_ENV=production
DATABASE_URL=postgresql+psycopg://liftlab_app:REPLACE@127.0.0.1:5432/liftlab
AUTH_SECRET=REPLACE_WITH_AT_LEAST_32_RANDOM_CHARACTERS
REGISTRATION_OPEN=false
AUTH_INVITE_CODE=REPLACE_WITH_PRIVATE_INVITATION_CODE
APP_SUPPORT_EMAIL=

WECHAT_APP_ID=
WECHAT_APP_SECRET=

SMTP_HOST=
SMTP_PORT=465
SMTP_SSL=true
SMTP_FROM=
SMTP_USERNAME=
SMTP_PASSWORD=
```

`AUTH_SECRET` 签名会话，同时用于验证码 HMAC 和邮件队列加密。更换它会使全部会话失效，并使旧队列邮件不可解密；应在维护窗口清理失效队列、重新发送验证邮件。正式运营时可再拆分密钥和轮换策略。

当前内测默认关闭开放注册，邀请码在服务器私有环境文件中生成；可更换为自己保管的邀请码。准备公开注册时再设置 `REGISTRATION_OPEN=true`，并先完成发送额度与公开服务配置。

开发模式未配置 `AUTH_SECRET` 时，会在运行数据目录创建本机随机密钥文件；生产模式必须显式配置。没有任何匿名业务访问或默认测试账号。

## 微信开放平台需要申请什么

1. 在微信开放平台创建**移动应用**，完成相应审核并开通微信登录能力。公众号、小程序 AppID 不能直接替代。
2. 安卓包名目前为 `com.liftlab.liftlab`；正式发布前确定最终包名。
3. 在平台配置实际安装包的签名。调试签名与正式签名不同，必须与待测试 APK 一致；不能只填写包名。
4. 将 AppID 填入后端 `WECHAT_APP_ID`，AppSecret 填入后端 `WECHAT_APP_SECRET`，重启后端。客户端从服务器获取公开 AppID，AppSecret 不进入 APK。
5. 客户端已通过 fluwx 插件接入 SDK，插件合并安卓微信可见性与 `wxapi.WXEntryActivity` 回调入口；最终以 APK 合并清单为准。
6. 在已安装微信的安卓手机上测试成功授权、取消授权、微信未安装、状态过期与重复登录。

OAuth 流程：App 创建随机 verifier → 后端登记其 SHA-256 摘要并签发随机 state → SDK 带 state 向微信请求授权 → App 将 code、state 和 verifier 送后端 → 后端消费 state 并向微信换取/验证身份 → 创建或找到账号 → 签发自己的令牌。

这里的 verifier 绑定是 App 与自有后端之间的防护，不表示微信移动 SDK 提供标准 PKCE 参数。state 单次使用，有效 5 分钟；App 被系统终止导致待处理 verifier 丢失时，需重新发起登录。

微信身份使用服务器验证的 `(AppID, openid)` 唯一绑定。本期不依据昵称、头像或客户端传来的 openid 登录，也不自动合并不同平台/账号的 UnionID。邮箱账号可在“账号与安全”显式绑定微信；微信已绑定其他账号时拒绝合并。

目前客户端真实 SDK 流程以安卓为目标。网页不提供微信扫码登录；iOS 还需要 Universal Links、签名与平台配置以及真机验收。

## 验证邮件

配置支持 TLS 的 SMTP 服务。465 使用 `SMTP_SSL=true`；587 使用 `SMTP_SSL=false` 并强制 STARTTLS。
完成服务商要求的发信域名认证、SPF/DKIM 等配置。用户名、授权码由服务商提供。

验证码有效 10 分钟，单次使用，最多尝试 5 次；发送至少间隔 60 秒，并有 IP/账号额度。验证消息加密后进入 PostgreSQL 队列；`liftlab-mail.timer` 每分钟调用 `scripts/send_mail.py`，最多重试 3 次。

没有 SMTP 时注册与找回密码返回 503，界面明确说明未配置；不会返回开发验证码或假装发信成功。已有账号的密码登录不依赖 SMTP。

## 数据库部署与迁移

首次安装 PostgreSQL：

```bash
bash deploy/linux/provision-postgres.sh
```

仅在目标服务器执行，会安装 PostgreSQL、创建专属数据库/角色和受保护的配置文件。发现同名现有数据库但无对应配置时停止，避免覆盖。不会迁移电脑的个人记录。

版本安装器用 owner 角色运行：

```bash
python -m alembic upgrade head
```

再为运行账号授予所需表/序列权限。不能将数据库 URL 写进 App，不能开放 5432 公网访问。

SQLite 到 PostgreSQL 的首次切换要求旧云端个人记录为空；若出现记录，安装器停止并要求明确用户归属。旧 SQLite 保留为受保护快照。新库产生数据后，不能直接切回旧 SQLite 并认为数据完整。

每日备份现在按 `DATABASE_URL` 选择 PostgreSQL `pg_dump`，归档 `database.dump` 与媒体；本地 SQLite 仍可备份。备份不包含环境配置。当前定时策略保留最近 7 份，同机备份仍需补充异地私有存储。

## 首个运营账号

开发者可在受控终端加载后端环境，再运行：

```bash
python scripts/manage_account.py create --email YOUR_EMAIL --admin
```

密码在终端隐式输入，不通过命令行参数或日志传递。这是运营者手工确认身份后的创建工具，不是公开注册接口。
给已登录的微信用户授予系统库管理权限：

```bash
python scripts/manage_account.py promote --user-id USER_UUID
```

普通用户只能读取系统食物/动作库，客户端也隐藏维护按钮。管理员没有默认读取其他用户健康画像或聊天的接口。

## Flutter 与手机

```powershell
& D:\ai-train\.tools\flutter\bin\flutter.bat build apk --debug --dart-define=API_BASE=https://api.YOUR_DOMAIN
```

主页面由登录状态控制，退出时清理个人页面、缓存和本地提醒；再次登录从服务器加载本人的提醒设置。访问令牌仅保存在内存，刷新令牌保存在平台安全存储，普通请求和 multipart 上传统一携带 Bearer 凭据。

浏览器预览将刷新凭据仅保存在内存，刷新网页需重新登录；本期不通过 localStorage 存储凭据。公开 Web 版本的持久登录需另做 HttpOnly Cookie/CSRF 方案。

已确定正式接口域名 `api.lianbanfit.top`，域名备案和公网HTTPS尚未完成。当前0.2.0正式签名测试包使用Tailscale私有HTTPS，已覆盖安装到荣耀手机并完成登录、首次画像引导验证；保持手机Tailscale连接即可脱离USB访问云端。测试网络说明见 [PRIVATE_MOBILE_TEST.md](PRIVATE_MOBILE_TEST.md)，签名说明见 [ANDROID_SIGNING.md](ANDROID_SIGNING.md)。

## 测试与已知发布前事项

- 后端单元/接口测试：`python -m pytest backend tests -q`。
- PostgreSQL 并发测试需使用**一次性测试数据库**设置 DATABASE_URL；测试会删除该测试库中的用户，严禁指向生产库。
- Flutter：`flutter analyze`、`flutter test`、`flutter build apk --debug`。
- 真实微信授权、真实邮件送达、正式域名移动网络访问仍需外部配置和真机验收。现有Android签名及私有HTTPS移动网络访问已核验。
- 用户协议与隐私政策目前是明确标注的内测草案，公开发布前补全主体、第三方服务清单、保存期限和联系信息。
- 对话、生成计划、截图分析和复盘当前AI限制为每用户6次/分钟、100次/天、同一时刻1个请求。新进阶接口`/progression`尚未纳入此统一限制，公开测试前应补齐；费用统计也尚未接入。

参考：[微信官方移动登录文档](https://developers.weixin.qq.com/doc/oplatform/Mobile_App/WeChat_Login/Development_Guide.html)、[fluwx](https://pub.dev/packages/fluwx)、[FastAPI 认证](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)。
