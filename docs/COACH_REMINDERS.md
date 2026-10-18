# 虚拟私教与训练、饮食提醒

## 入口与行为

- 首页对话、侧边栏、提醒页面展示虚拟 AI 教练头像。默认昵称“林教练”，可以修改。
- 在“我→私教提醒”或侧边栏“私教提醒”中，选择训练星期、训练开始时间和提前提醒分钟数；到点训练与提前准备是两种独立循环提醒。提前时间为0时只安排到点提醒。
- 开启饮食提醒后，可以单独选择早餐、午餐和晚餐，修改每餐时间。三餐按天重复；不会因为未记录就推断用户没吃饭。
- 所有时间明确采用 `Asia/Shanghai` 北京时间，不跟随设备时区自动漂移。训练前提醒跨午夜时会正确移到前一日。
- 开启的训练日数量和时间同步到用户画像，供 AI 计划使用；没有启用训练提醒时，不重写用户原先的训练安排。对话中的时间先作为画像信息保存，正式提醒仍在设置页确认。
- 提醒文案由本地规则生成，使用教练昵称及增肌/减脂目标。它们是提醒文案，不是模型即时回复；不会在每次到点时调用付费 API。锁屏通知不展示年龄、体重、伤病描述。

## 手机与网页

Android/iOS：设置保存在手机本地，系统安排循环通知；既有提醒不依赖电脑连接或 API 可用性。点击通知跳转训练计划/饮食页面。后台和锁屏使用系统通知，非强制播放语音。

Android：配置通知权限、启动/更新后恢复接收器、通知小图标、Java 17 和 desugaring；使用 `inexactAllowWhileIdle`，不申请精确闹钟权限。应用首次打开不主动请求通知权限，用户保存开启的设置或测试通知时才请求。拒绝权限会明确显示“设置已保存但未获允许”，不会假称通知已安排。手机省电限制可能延后或阻止后台提醒，须在实际荣耀手机上验证。

Web：每15秒检查当前分钟，页面处于前台时显示带教练头像的提示。同一个提醒当天去重，刷新后同一分钟不会重复。网页关闭、切到后台或设备休眠后，不补发历史通知；当前未实现网页后台推送。

“测试教练提醒”可测试原生通知或网页内提示。关闭开关并保存会取消本功能旧通知，不影响其他模块通知。Android 强行停止应用后不能保证提醒送达，应重新打开应用。

手机本地设置可离线查看和修改；服务器同步失败时仍保留本机设置，显示同步失败原因。其他设备上使用“载入已保存安排”，检查后保存到该设备才生效。设备缓存是实际通知安排，后端记录是画像及跨设备安排副本。

相关官方说明：

- [flutter_local_notifications 配置与后台限制](https://pub.dev/packages/flutter_local_notifications)
- [Android 通知权限](https://developer.android.com/develop/ui/views/notifications/notification-permission)
- [timezone 时区规则](https://pub.dev/packages/timezone)

## 文件与接口

- 原创教练资产：`mobile/assets/coach/liftlab_coach.png`，静态虚拟角色插画，不是动作教学素材。
- 角色组件：`mobile/lib/coach_avatar.dart`。
- 提醒计算：`mobile/lib/reminders/reminder_settings.dart`。
- 本地存储、通知安排与网页提醒：`mobile/lib/reminders/coach_reminders.dart`。
- 配置页面：`mobile/lib/reminders/reminder_page.dart`。
- 服务端设置：`backend/reminders.py`，`GET/PUT /api/coach/reminders`，SQLite `coach_reminders`。
- 通知权限/重启接收器：`mobile/android/app/src/main/AndroidManifest.xml`。

## 形象生成记录

使用内置 image_gen 工具生成，原始文件复制进工作区后以 Flutter 资产打包。没有使用 API/CLI 备用路径，也不依赖项目模型密钥。实际生成提示词如下：

```text
Create one polished original virtual fitness coach character avatar for the LiftLab mobile app. Stylized 3D illustration, friendly approachable adult Asian coach, short dark hair, natural athletic build, wearing a plain forest green training T-shirt matching #244b3c, small warm smile, one hand giving an encouraging thumbs-up. Waist-up portrait facing the viewer, centered composition, entire head and hands visible with comfortable margins. Soft studio lighting, modern calm fitness companion aesthetic. Plain warm ivory background matching #f5f5ef. No words, no logos, no watermarks, no medical equipment, no exaggerated bodybuilding physique. This is a fictional AI character, not a real-person portrait. Deliver a square image suited to both a small circular chat avatar and a larger coach introduction card.
```

## 验证范围

自动测试覆盖时间/星期范围、非法设置不写画像、画像同步、跨午夜和周日/周一边界、北京时间换算、0分钟提前提醒、前台去重/持久化/关闭、原生循环安排参数、离线恢复和权限拒绝。原生通知测试使用模拟平台通道；真实锁屏通知、重启恢复、荣耀省电策略和 iOS 均仍需真机验证。之前用户要求暂不更新手机，因此本次只构建 APK，不自动安装。
