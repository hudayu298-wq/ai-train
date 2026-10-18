# 练伴 Android 正式签名与备案特征

2026-10-18 已生成正式签名并完成 release APK 构建与 apksigner 核验。安装名称“练伴”，包名 `com.liftlab.liftlab`，证书 MD5 为 `EE473B11FBF59CC96EB26CF91334DC92`，证书有效期至 2054-03-05（UTC）。备案可复制资料见 [lianban-app-filing.txt](assets/filing/android/lianban-app-filing.txt)。

## 创建方式

使用 JDK 的 keytool 生成长期使用的 RSA-3072 / SHA256withRSA 自签名应用证书，保存为 PKCS12 密钥库。证书主体采用应用技术名称，不冒用企业或个人法定身份。有效期 10000 天。

项目使用 `scripts/create_android_signing.py` 完成生成和配置；口令用密码学安全随机数创建，不放入命令行参数、不输出到聊天或日志。后续运行检测到已有签名时保留原密钥，不自动换证书。

```powershell
.venv\Scripts\python.exe scripts\create_android_signing.py --keytool 'C:\Program Files\Java\jdk-17\bin\keytool.exe'
```

## 私有文件位置

- 密钥库：`%USERPROFILE%/.android/lianban-signing/lianban-release.p12`
- 本机 Gradle 配置：`mobile/android/key.properties`，包含密钥库路径、别名及口令。

Windows 文件 ACL 限制为当前用户读取。配置与密钥库不提交 Git，APK 不包含密钥库或口令。请将这两项备份到自己控制的加密存储中；不要把口令、私钥或整个密钥库发到聊天。它们用于以后持续签署升级包，应长期保管。

## release 构建

`mobile/android/app/build.gradle.kts` 从本机配置读取正式签名。release 不再回退到 debug 签名，缺少必要配置时构建失败；debug 继续使用原来的调试签名。

```powershell
cd mobile
..\.tools\flutter\bin\flutter.bat build apk --release --dart-define=API_BASE=https://api.lianbanfit.top
```

此接口域名用于备案后的部署，当前公网入口未启用。0.2.0测试包另使用Tailscale私有HTTPS，已用同一正式签名覆盖安装并验证登录；见 [PRIVATE_MOBILE_TEST.md](PRIVATE_MOBILE_TEST.md)。正式签名包不能直接覆盖不同签名的旧调试包。

## 从实际 APK 导出备案信息

```powershell
.venv\Scripts\python.exe scripts\export_android_filing.py
```

脚本执行 Android apksigner 验证并读取 APK 内的证书，核对它与生成的 release 证书一致，同时核对包名和安装名称，再导出：

| 文件 | 用途 |
|---|---|
| `docs/assets/filing/android/lianban-app-filing.txt` | 备案三个字段的汇总与复制说明 |
| `docs/assets/filing/android/lianban-public-key-modulus.txt` | 公钥字段：RSA 模数十进制 |
| `docs/assets/filing/android/lianban-signature-md5.txt` | 签名 MD5：证书指纹十六进制，无冒号 |
| `docs/assets/filing/android/lianban-app-identity.json` | 可机器读取的证书、包名与 APK 校验信息 |
| `docs/assets/filing/android/lianban-signing-cert.pem` | 公共证书 |
| `docs/assets/filing/android/lianban-public-key.pem` | 标准 PEM 公钥，供需要该格式的系统使用 |

以上都是公开信息，可以用于备案；它们不包含私钥。“APK SHA256”仅作构建文件校验，不能填入“签名 MD5”字段。

公钥模数是从 APK 证书中提取的 RSA 整数。华为云当前文档要求 Android 公钥填写 APK signature 模数，签名 MD5 填证书指纹；不要将 PEM 整段、公钥指纹或 APK 文件 MD5 混用。

若未来使用商店托管签名或证书升级，最终分发给用户的签名可能变化，需要以该实际签名重新核对备案和第三方平台配置。

参考：[Flutter 正式签名](https://docs.flutter.dev/deployment/android#sign-the-app)、[Android apksigner](https://developer.android.com/tools/apksigner)、[华为云特征信息](https://support.huaweicloud.com/usermanual-icp/zh-cn_topic_0000002085120221.html)。
