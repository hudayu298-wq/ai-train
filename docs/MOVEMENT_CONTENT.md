# 关节动作分类、示意动画与AI共用资料

## 分类与字段

动作库按关节动作模式分类，训练部位作为独立筛选和标签：水平推、垂直推、水平拉、垂直拉、蹲、髋铰链、髋伸展、分腿屈伸、肩水平内收、肩外展、肩水平外展/外旋、肘屈曲、肘伸展、膝伸展、膝屈曲、踝跖屈、核心抗伸展、核心抗侧屈。

食物库按谷物薯类、肉蛋鱼、乳制品、豆类豆制品、蔬菜、水果、坚果种子、油脂分类，生熟状态仍独立记录。

共用字段：`movement_pattern`、`joint_actions`、`body_regions`、`primary_muscles`、`secondary_muscles`、`technique`。technique包括准备姿势、执行步骤、变式细节、注意事项、常见问题观察点、影像不可推断项、来源与审核状态。

## 同一份资料供页面与AI使用

```
exercise_content.json基础资料 + SQLite用户维护字段
                     ↓ enrich()
       动作库详情 / 实时训练准备页面
                     ↓ analysis_context()
      AI系统要求 + 动作资料 + 用户真实截图
                     ↓
        可见证据、引用截图索引与复核建议
```

原始资料在`backend/data/exercise_content.json`，编排与提示词在`backend/exercise_content.py`。用户编辑文案后，页面和下一次AI请求使用更新后的内容。每次分析保存完整参考快照、资料版本与SHA256摘要，历史分析不会被新文案追溯替换。

`GET /api/library/exercises/{id}/analysis-context`可查看准备好的共用上下文。已有上传录像可通过`GET /api/media/{id}/analysis-context`取得对应动作上下文，但该接口不自动解码或分析录像。

## 动图

38个内置动作各有原创GIF与静态封面，位于`backend/assets/exercise-demos`，由`/assets/exercise-demos/{id}.gif`提供。图中橙色表示主要动作关节。动图是二维关节示意，并非真人示范、3D骨骼运动测量或已验证的合格动作模板。静态支撑类展示建立/保持姿势，不把它当动态计次练习。

生成脚本：`scripts/build_exercise_content.py`、`scripts/build_exercise_demos.py`；需要Pillow和Windows微软雅黑字体。发布服务器只需使用已生成资源，无需安装字体或生成工具。

## 内容状态

动作细节是项目整理的教学草稿，不声称已获专业验证。卧推、传统硬拉和低杠深蹲同时保留Starting Strength官方配套文章的参考信息。用户尚未提供《力量训练基础》实际版本章节，所以没有编造页码或宣称核验书籍全文。

`docs/starting_strength_rules.json`中的候选规则被保留为`reference_only`：可展示并进入参考上下文，尚不允许AI把它们报告为已识别问题。高杠深蹲不套用低杠规则。

当前只允许实验性观察点，且必须满足最低截图数量与视角要求；看不清时应拒绝判断。模型不能声称影像测得肌肉激活、疼痛、腹压、伤病风险、完整三维脊柱或细微肩胛状态。示意图角度不能转换成判错阈值。

核心三项的身份、器械、重量口径与拍摄定义固定；教学文案可维护。已有实时计次不调用云端视觉模型，也不因新增文案自动开启新的实时纠错规则。

## 实验性截图观察

在动作库详情选择同一动作的2–6张JPG/PNG截图（每张不超过2MB，总计不超过10MB），并注明角度。图片发送至后端和已配置的视觉模型。此入口不能代表连续录像分析，也不用于训练过程即时播报。

配置独立的、支持图片输入和JSON输出的模型：

```dotenv
VISION_API_KEY=你的视觉模型密钥
VISION_BASE_URL=服务商API基础地址
VISION_MODEL=支持图片输入的模型ID
```

`GET /api/movement/status`读取配置状态。`POST /api/movement/analyze`接收：

```json
{"exercise_id":"bench","camera_view":"front","frames":[
  {"mime_type":"image/jpeg","image_base64":"图片Base64内容"},
  {"mime_type":"image/jpeg","image_base64":"图片Base64内容"}
]}
```

结果只允许引用该动作的可用观察点及真实请求中的截图索引，建议文案来自共用资料。该接口不存储原始截图，仅保存文本与参考快照。无有效观察点时返回`insufficient_evidence`；没有视觉模型配置时提示503，不制造分析结果。

当前通过的是模拟模型请求和界面测试；真实模型尚未配置，识别准确率和连续录像/实时纠错仍待后续验证。
