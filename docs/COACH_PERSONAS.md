# 四位 Q 版健身教练

首页教练为可拖动的 Q 版人类健身教练，使用精致 3D 卡通 PNG 角色和 Flutter 动画。当前采用黑白灰与蓝色界面，不使用绿色主题；设计说明见 `UI_REDESIGN.md`。

| 教练 | 形象 | 性格 | 独立提示词 |
| --- | --- | --- | --- |
| 阿衡 | 短发男教练、蓝色运动背心、肩臂肌肉 | 稳健陪练：耐心、平实，重视持续与控制 | `backend/prompts/coaches/steady.md` |
| 小燃 | 高马尾女教练、橙色运动上衣与黑色瑜伽裤 | 活力搭子：轻快、积极，把目标拆小 | `backend/prompts/coaches/energetic.md` |
| 阿策 | 戴眼镜男教练、灰蓝运动背心、肩臂肌肉 | 理性规划：条理清楚，区分记录和估算 | `backend/prompts/coaches/analytical.md` |
| 棉棉 | 短发女教练、紫色运动上衣与瑜伽裤 | 温柔支持：尊重感受、选择和恢复节奏 | `backend/prompts/coaches/gentle.md` |

## 怎么使用

- 点击主页右上角“切换桌宠教练”，或桌宠下方“换教练”打开选择界面。“我→私教提醒”中也有入口。
- 拖动完整桌宠调整位置；点击角色会轻弹回应，长按可换教练；点减号收起成小标签，点标签恢复。
- 待机会轻轻浮动呼吸；等待 AI 时倾斜并显示思考图标，收到回复时轻弹回应，提醒时显示提醒图标和教练气泡。待机时不常驻显示对白气泡。系统开启“减少动态效果”时停止循环动画，切走主页也停止动画。
- 桌宠位于聊天记录区域，保留底部输入框。小窗口/键盘压缩区域时自动缩成小标签，拖动限制在区域内。
- 四种性格共用现有模型 API，不需要四套模型。切换会更新角色、提示词、问候语和训练/饮食提醒；用户画像及历史记录保留。
- 角色选择在本机持久化，并同步提醒设置到服务器。聊天请求携带明确的 `coach_id` 和昵称，旧消息保留当时的教练 ID/昵称，不随切换重命名。

## 提示词与数据来源

`backend/prompts/fitness_coach.md` 为共同的画像提取、证据、结构化输出及健康边界。服务端实际提示词 = 共同提示词 + 当前教练独立性格提示词，版本 `coach-2.2`，已统一为人类教练形象。历史其他教练的回复仅作为资料。

选择界面每位教练都有“查看性格提示词”；侧边栏“私教提示词”显示当前选择的完整生效提示词。修改文件后重启后端。人格只改变交流方式，不改变动作可观测性、RM参考或画像验证条件。

`GET /api/coach/personas` 返回四位教练资料；`GET /api/coach/prompt?coach_id=gentle` 返回该教练的共同/独立/完整提示词。`POST /api/coach/messages` 新增可选 `coach_id`、`coach_name`；输出和历史包含实际使用的身份。

人物元数据与离线提醒文案以 `backend/data/coach_personas.json` 为源。修改后运行：

```powershell
.\.venv\Scripts\python.exe scripts\build_coach_personas.py
.\.tools\flutter\bin\dart.bat format mobile\lib\coaches\coach_persona.dart
```

该脚本生成 Flutter 的 `mobile/lib/coaches/coach_persona.dart`。外形与动画在 `coach_pet.dart`，选择界面在 `coach_picker.dart`。最终素材位于 `mobile/assets/coach/chibi/`，通过 Flutter 资产清单打包。生成方式、文件清单、完整提示词与动画范围见 `COACH_ART.md`；旧真人风格素材不打包。

## 验证与范围

测试覆盖四套独立提示词实际进入模型请求、未知 ID 拒绝、切换身份与旧消息身份保留、客户端选择后发送正确 ID/昵称、拖动边界、收起恢复、不同性格提醒，以及原有画像、计划、饮食和本地通知功能。真实语言风格效果仍需配置模型密钥后评估。

这是 App 内桌宠。当前不涉及 Android 系统桌面悬浮窗权限、Windows 独立常驻窗口或 Codex 宠物插件。Android 包构建后仍遵循先前“暂不更新手机”的要求，不自动安装。
