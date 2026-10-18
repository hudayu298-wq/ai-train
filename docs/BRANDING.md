# 练伴：名称与 App 图标

## 本次交付

显示名称为 **练伴**。Android 安装名称、iOS 显示名称、Flutter 标题与侧边栏、Web 标题及 PWA 名称已同步。

图标由内置 image_gen 工具生成，采用蓝色背景、白色对话气泡和负形哑铃。图形表达健身训练与 AI 陪伴，使用不含文字的标志以保证小尺寸可读性；外部方形画布不预裁圆角，由各平台应用图标形状处理。

| 文件 | 用途 |
|---|---|
| `docs/assets/filing/lianban-icon-512.png` | 备案上传用：512×512 PNG，无透明通道，94,236 字节，小于 100KB |
| `mobile/assets/branding/lianban-icon-1024.png` | 1024×1024 高清图标 |
| `mobile/assets/branding/lianban-icon-source.png` | 原始生成图，1254×1254，保留供后续尺寸导出 |
| `mobile/assets/branding/generation-prompt.txt` | 本次内置工具使用的完整生成提示词 |
| `docs/assets/filing/icon-exports.json` | 导出尺寸、文件与大小清单 |

Android 各密度启动图标、iOS AppIcon 集、Web/PWA 图标和 favicon 均使用同一图案。iOS 尚未在 macOS/Xcode 构建验证。

尺寸转换与 PNG 编码由 `scripts/export_app_icons.py` 执行，只进行机械缩放和编码；备案图使用索引色压缩以满足文件大小限制。

```powershell
.venv\Scripts\python.exe scripts\export_app_icons.py
```

本次修改显示名称，不调整包名、账号标识、数据库归属或令牌签发方。当前包名仍为 `com.liftlab.liftlab`。

备案名称应填“练伴”，对应安装后的显示名称。正式安卓签名已生成并通过 release APK 核验，备案公钥和 MD5 见 [ANDROID_SIGNING.md](ANDROID_SIGNING.md)；提交时使用正式签名资料。
