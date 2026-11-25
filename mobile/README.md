# 练伴 Flutter客户端

当前版本0.5.1+8，Android与Web共用业务界面。项目根目录为`D:\ai-train`。

新会话先读根目录[README](../README.md)、[AGENTS](../AGENTS.md)、[PRD](../docs/PRD.md)、[架构](../docs/ARCHITECTURE_AND_AI.md)与[开发状态](../docs/DEV_STATUS.md)，不要按Flutter默认模板重新创建工程。

```powershell
Set-Location D:\ai-train\mobile
..\.tools\flutter\bin\flutter.bat analyze --no-pub
..\.tools\flutter\bin\flutter.bat test --no-pub
..\.tools\flutter\bin\flutter.bat build web --release --base-href /app/ --no-pub
```

缺依赖先执行`flutter pub get`。相机、端侧姿态、语音、通知与微信插件包含原生配置，不能用Web测试替代Android真机验收。APK签名和API_BASE设置见[新会话交接](../docs/DEVELOPMENT_HANDOFF.md)；用户当前偏好仅保存APK。

主入口`lib/app.dart`，对话`lib/coach_chat.dart`，计划`lib/user_plan_editor.dart`，动作库`lib/library_page.dart`，实时训练`lib/live/`。按关节动作筛选通过`joint_action_categories`多归属与`body_regions`联动；新增目录素材不代表有新增实时检测器。

本地Web构建与云端后端部署分开。APK连接私有云端时，新本地代码或资料库不会自动出现于手机。
