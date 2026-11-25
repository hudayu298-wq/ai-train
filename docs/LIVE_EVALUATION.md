# 伴练证据与本地计次评测

2026-10-25；对应PRD的LIVE-03/04/05。当前为本地0.5.1增量，未部署云端或更新APK。原则来自对评分标准不确定性的讨论，以下是本项目工程设计，不把康复研究分数迁移为杠铃训练合格线。

## 用户入口与证据

“AI陪训”选择三大项之一，点击“证据回放与双人标注”；Web也可运行。实时训练页另有相同入口。先点“运行合成演示”，查看两个周期及一次多人返回拒判；展开证据卡查看组次、起止时间、周期内二维角度范围、最低关键点可见性和样本数。它们不是实际关节活动度、识别正确概率或动作合格结论。

实时页按无人物、多人返回、关键点缺失、低可见性、出框、无效几何、帧中断、乱序、跟踪侧变化、延迟、帧格式和推理错误分别说明暂停原因。信号失效重置未完成周期，低置信度不继续凑次数；不足600毫秒的周期拒判，结束组的半周期不计数。0.7可见性、800毫秒稳定、500毫秒间断/检测耗时、计次角度和600毫秒等仍是开发参数，未通过真实训练质量验证。

SDK只返回一人时，App不能据此排除画面中的其他人；机位与身份仍手动确认。证据不包含杠铃跟踪、脊柱内部状态或伤害风险判断。实际重量/次数/RPE仍要在训练日志确认。

## 本人轨迹缓存

实时页开关默认关闭。本人开启后，仅缓存本页关键点与可见性、时间、画面比例、检测耗时、是否训练及SDK返回人物数；不保存像素、录像或音频，不上传、不供AI使用。启用时重新稳定入框，使回放包含独立起始状态。训练中允许关闭并立即清除；退出或进入回放前停止相机并清除缓存。最多6000帧或约4MB，到限停止采集且说明；较长训练需分批导出，不能假装完整覆盖。

点击“查看本地轨迹JSON”后可自行选择复制保存；本页不会自动复制或写文件。导出的副本由本人管理，关闭页面不会删除本人自行保存的副本。正式训练记录和轨迹缓存各自独立。真实评测录像需另外授权、另外采集保存在本机，当前不支持自动录制或自动从视频提取关键点。

## 格式与标注

`lianban-pose-replay-1`每例包含：

| 字段 | 说明 |
|---|---|
| exercise_id | bench / squat（高杠）/ deadlift（传统），不混动作变式 |
| source | synthetic_demo / user_capture / annotated_video_trace；不能把合成来源改名冒充真实录像 |
| subject_id、split | 一致的匿名受试者编号，dev或test；真实资料不要进入Git |
| camera_view、video_reference | side/front/unknown，本地录像编号/文件名文字；工具不读取文件，不验证引用真实性 |
| rule_version、engine_source_sha256、estimator | 规则版本、构建时可注入的引擎SHA及姿态模型说明；底层ML Kit模型构建号未提供时明确标记，不能补造 |
| frames | 严格递增毫秒时间、aspect、active、pose_count、detection_ms、points；每个关键点是[x,y,可见性]，数值有限、可见性0–1 |
| annotations | 最多两份：不同rater_id、independent=true、judgeable布尔值、rep_ends_ms整数数组；无法判断时不填确定结束时刻 |

界面可填写两位标注者各自的匿名编号、结束时刻、可判断与独立标注声明。标注者需分别观看实际录像，不先看算法结果或另一份答案；结束时刻对齐轨迹的训练帧。空数组可表示明确0次，但“无法判断”不能当0次。录像引用、独立性和专业资格不能由工具自动证明，现场组织者需保留采集、标注与权限证据。

两人次数与逐次结束时刻一致（允许300毫秒产品容差，不是研究标准），同版本、侧面、真实标注录像来源且证据未截断时，才计算计次绝对误差及300毫秒内的一对一事件precision/recall。两者都无事件时precision/recall为null，不填1。演示、标注缺失、无法判断、分歧、缺录像、版本不匹配等只展示检测过程，不给准确率结论；不能只报告可判样本而隐去排除数。

报告包含分歧、不可用帧原因分布、可观察训练帧比例和采集时检测耗时P95。P95仅是轨迹中记录的处理时间，合成示例的12毫秒不代表实际手机、端到端或耳机延迟。当前评测仅覆盖计次及拒判流程，没有问题点级姿态纠错precision/recall、专家一致性ICC或安全验证。

## 批量命令

在`D:\ai-train\mobile`运行：

```powershell
..\.tools\flutter\bin\dart.bat run tool/evaluate_live.dart test/fixtures/synthetic_live_manifest.json ..\.tools\live-evidence\replay-report.json
```

manifest为`{"cases":[...上述每例对象...]}`。仓库示例是三大项几何合成轨迹，无真实视频或专家标签；预期dev三例、可比较0例、计次MAE为null，不能用来发布识别质量。工具先校验整批：受试者不能跨dev/test，同一轨迹或录像引用不能重复计入，未分配受试者ID需补全；这些检查不能替代实际数据分组审计。

结果保留manifest、引擎/回放/评测源码SHA及每例输入SHA、排除数与分歧。`quality_validation=not_performed`，`release_gate=not_evaluated`；没有自动激活。保留失败命令/报告，不改分母、标签或来源把未通过变成通过。先固定开发集，再在未参与调参的新受试者/场景上测试。

构建Web时可绑定引擎源码指纹：

```powershell
$liveEngineSha = (Get-FileHash lib/live/coaching_engine.dart -Algorithm SHA256).Hash.ToLowerInvariant()
..\.tools\flutter\bin\flutter.bat build web --release --base-href /app/ --no-pub "--dart-define=LIVE_ENGINE_SHA=$liveEngineSha"
```

未注入时明确写unrecorded，不冒充已绑定；未来APK构建也需注入并单独验证。模型/规则/机位改变后，不直接拼接旧版本的纵向分数。本次验收范围及证据见[DEV_STATUS](DEV_STATUS.md)。
