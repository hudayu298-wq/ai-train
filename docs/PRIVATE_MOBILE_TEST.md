# 练伴：手机连接云端进行私有测试

此方式用于授权设备上的开发测试。正式域名仍为 `api.lianbanfit.top`，公网入口尚未启用。

## 0.2.0 画像引导与计划进阶

2026-10-18：0.2.0（versionCode 4）已通过USB覆盖安装到荣耀Magic7 Pro，真机已登录并进入画像引导。手机端健康接口和登录配置接口均通过有效TLS返回200。首次进入会配置画像、自动生成待确认的整体周期计划；RM位于“我”，记录、复盘及历史位于独立侧边栏模块。进阶详情见 [AI训练计划](AI_PLANS.md)。

文件：`.tools/apks/lianban-private-test-0.2.0-arm64.apk`，70,774,854字节；SHA256 `25fb969efc812207ff8551dcc3a98a619bd4fb8f040fc2968c9cfa5d106fc96c`。正式签名、Room数据库构造函数、通知图标及私有API地址已核验。0.1.2保留供回退，不删除应用或云端数据。

私有下载地址已原子更新为0.2.0，完整APK哈希、下载长度、分段读取、HTTPS证书、健康检查及未登录401均已核验。

本地后端及部署相关测试87项通过（2项需要PostgreSQL而跳过）；服务器独立PostgreSQL的86项后端测试通过；Flutter 30项测试通过、静态分析通过。真实DeepSeek在独立测试数据库通过三天/四周计划生成、伤病单独提示、显式确认、首次训练后保持负荷的联调；测试数据库已移除。正式服务已部署新后端，未替真实用户填写画像或确认计划。

以下0.1.2段落保留此前登录与启动修复记录；以本节说明的手机版本为准。

2026-10-18：服务器与荣耀手机已入网，Tailscale 1.104.1 的私有 HTTPS Serve 已验证。正式签名的 ARM64 测试 APK 已构建并通过 apksigner 验证。健康接口返回正常，未登录访问画像返回 401，APK 下载响应的长度、类型与分段读取核验通过。0.1.2 修复版已通过 USB 覆盖安装，已实际显示登录页，用户已确认可以登录。备案 APK 已单独留存于本机 `.tools/apks/lianban-filing-release.apk`，该旧包只作原始身份核验留存，不作为可用安装包。

测试接口：`https://lianban-test.tail33f536.ts.net`。手机下载安装：<https://lianban-test.tail33f536.ts.net/downloads/lianban-test.apk>，需保持 Tailscale 已连接。Let's Encrypt 证书有效期至 2027-01-16（UTC），由 Tailscale 管理续期。证书申请初期曾因 DNS 传播出现验证失败，最终签发并通过正常证书校验；没有关闭 TLS 验证。

此前测试包：0.1.2（versionCode 3），70,709,226 字节；SHA256 `d7f0e5b319a4b28fa61436ab4039eb246671e2f1649eea04e93d2c0a65a7be6c`。包名与备案证书不变；构建参数 `--target-platform android-arm64`，Flutter 引擎为 ARM64，适配此次荣耀 Magic7 Pro。

## 连接结构

手机练伴 → 手机 Tailscale → 私有 HTTPS Serve → 云端 `127.0.0.1:8000` → 本机 PostgreSQL。

服务器与手机必须加入同一 tailnet。Serve 受该网络的访问规则限制；应在 Tailscale 控制台把访问权限限制到测试设备与服务的 443 端口。不要启用向互联网公开服务的 Funnel。

## 服务器准备

Ubuntu 24.04 使用 `deploy/linux/prepare-private-test.sh` 安装官方稳定版软件源及客户端。

```bash
bash /tmp/lianban-prepare-private-test.sh
tailscale up --hostname=lianban-test --accept-dns=false --accept-routes=false --ssh=false --timeout=30s
```

使用命令显示的官方登录链接，以手机正在使用的账号完成服务器授权。不要把账号密码或 auth key 发到聊天或提交仓库。

本机云 DNS 为 `100.125.1.250`，与 Tailscale CGNAT 范围重叠；默认内核模式的防伪造规则会丢弃从 eth0 返回的 DNS 数据包，导致全部未缓存 DNS 查询超时。经 `dig`、`ip route get` 和防火墙丢包计数核验后，使用 `configure-private-test.sh` 切换为 userspace 模式，保留原服务器路由与 DNS 配置。`127.0.0.1:1055` 的 SOCKS5 入口仅用于本机验收私有 HTTPS，不对公网监听。

入网后，开启仅限 tailnet 的 HTTPS 服务：

```bash
tailscale serve --bg http://127.0.0.1:8000
tailscale serve status
```

若提示尚未开启 HTTPS，需由账号所有者按官方链接授权。以实际输出的 HTTPS 地址作为测试 APK 的 `API_BASE`。后端与数据库保持原有本机监听，Caddy 的公网服务保持停用。

## APK 构建与验证

```powershell
cd mobile
..\.tools\flutter\bin\flutter.bat build apk --release --dart-define=API_BASE=https://实际设备名.实际网络名.ts.net
```

沿用 [正式签名](ANDROID_SIGNING.md)。构建后应通过 apksigner 验证签名，核对名称、包名与证书指纹，再将 APK 单独保存供安装；不要覆盖备案留存包。

本次文件保存在本机 `.tools/apks/lianban-private-test-arm64.apk`；服务器路径 `/var/lib/liftlab/private-test/lianban-test.apk`。私有 Serve 只映射后端接口和这个 APK 文件，不映射数据目录。`deploy/linux/verify-private-test.py` 将不含凭据的核验结果保存为 `/var/lib/liftlab/private-test-verification.json`。

修复版另存为 `.tools/apks/lianban-private-test-0.1.2-arm64.apk`。上传新版本后使用 `deploy/linux/publish-private-apk.sh` 校验文件哈希并原子替换下载文件；不要向用户提供 0.1.0 或中间验证包 0.1.1。

如果手机原先安装的是 debug 签名，正式签名 APK 无法直接覆盖。卸载会删除手机本地数据，需先确认保留需求再操作；云端账号记录不因卸载手机应用而自动删除。

## 手机验收

1. Tailscale 显示已连接，服务器设备在线。
2. 手机浏览器访问实际私有 HTTPS 地址的 `/api/health`，确认正常 JSON 响应及有效证书。
3. 安装练伴测试 APK，使用云端测试账号登录。
4. 验证对话、画像、计划和饮食记录；上传、AI 调用及相机分别按实际配置验收。
5. 断开 USB，改用移动流量，再次访问并验证记录保存。

当前 SMTP 和微信登录尚未配置。若无已有账号，由运营者通过服务器的 `scripts/manage_account.py` 交互创建经过人工核验的测试账号；口令通过隐藏输入设置，不在聊天展示。网络连通不能替代模型、邮件或微信等功能的配置。

本次已通过交互窗口完成测试账号创建。用户自行设置密码，脚本和核验报告均不保存明文口令。普通测试账号不授予管理员权限。

## 正式包启动修复记录

0.1.0 在荣耀手机上的崩溃发生在 `androidx.startup.InitializationProvider`：WorkManager 无法实例化 `androidx.work.impl.WorkDatabase`。真机 DropBox 崩溃记录与 R8 `usage.txt` 均证实 `WorkDatabase_Impl` 的默认构造函数被删除。增加项目 ProGuard 规则，显式保留 Room 数据库子类的无参构造函数；继续保留代码压缩。

进一步真机检查发现，通知图标通过名称字符串查找，被资源压缩删除，导致 `invalid_icon` 并阻塞登录初始化。通过 `res/raw/keep.xml` 保留 `ic_coach_notification`，并核对实际 APK 的资源表。AuthGate 同时处理准备阶段异常，显示重试入口；清理未完成时不进入个人数据页面。

验证：登录相关 4 项测试通过（含启动插件失败后重试恢复），Flutter analyze 通过，正式签名 APK 构建通过，构造函数与图标均保留。USB 覆盖安装 0.1.2 成功，手机进程正常运行并显示登录页，用户确认已登录。没有卸载应用或清除应用数据。网络首次连接偶有中继延迟，用户重试后成功登录；公网备案入口仍未启用。

技术参考：[AndroidX 对 Room 构造函数保留规则的修复](https://android.googlesource.com/platform/frameworks/support/+/e4765e38e27a3f4d86188b996df97a52403dff46)。

## 停止测试

服务器执行 `tailscale serve reset` 可移除私有服务映射；`tailscale down` 断开服务器私有网络。也可在控制台撤销测试设备。备案完成后切换正式 HTTPS 地址并重新构建，不再依赖手机 Tailscale。

参考：[Linux 安装](https://tailscale.com/docs/install/linux)、[Android 安装](https://tailscale.com/docs/install/android)、[私有 HTTPS Serve](https://tailscale.com/docs/features/tailscale-serve)。
