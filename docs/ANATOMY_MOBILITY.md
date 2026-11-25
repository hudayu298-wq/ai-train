# 三大项解剖与活动度试点

本次新增内容属于 `foundation-20261022-v2`。历史v1与新候选的激活、评测和审核状态由知识库发布流程管理，升级代码不等于新内容已经发布或获得专业审核。`source_checked`表示编辑核对来源，不是解剖学专家、理疗师或临床审核结论。

## 解剖覆盖

`backend/services/knowledge_anatomy.py`通过`install_anatomy(sources,nodes)`扩展原有三大项知识；营养与周期扩展通过`knowledge_rules.install_principles`的独立入口安装。

本模块新增20块/组肌肉：肩袖四肌、斜方肌、大小菱形肌、前锯肌、竖脊肌群、多裂肌、腹直肌、腹内外斜肌、腹横肌、大/长/短收肌、股薄肌、臀小肌、髂腰肌；新增13种动作、2个关节/功能性复合体、12个骨性标志和1个测量原理，合计48条。原有4张动作卡补充准备、下降、转折/向心与结束阶段说明，新增的关系可追踪到肌肉、关节与骨性标志。

肩胛胸廓明确记录为功能性联系，**不是独立真性滑膜关节**。斜方肌、大收肌和髂腰肌保留分部/组成差异。腹横肌压缩腹部不伪造为某个关节动作。训练中的协同和稳定角色属于编辑应用说明，不能当作个体肌电、肌肉受力比例或由视频证明的结果。骨点用于理解附着和测量，未实现穿衣录像的自动骨点定位。

来源定位按英文肌肉名、教材节号或论文方法/表号保留；每条记录含人群、局限、引用、来源版本/访问日期以及内容使用说明。

| 来源 | 本次使用位置 | 边界 |
| --- | --- | --- |
| [UAMS 上肢教学表](https://medicine.uams.edu/neuroscience/education/medical-school-courses/human-structure-module/anatomy-tables/muscle-tables/muscles-of-the-upper-limb/) | 肩袖肌行 | 主要起止点与作用的概要 |
| [UAMS 下肢教学表](https://medicine.uams.edu/neuroscience/education/medical-school-courses/human-structure-module/anatomy-tables/muscle-tables/muscles-of-the-lower-limb/) | 内收肌、臀小肌和髂腰肌行 | 分部和多关节差异不能省略 |
| [UAMS 背部教学表](https://medicine.uams.edu/neuroscience/education/medical-school-courses/human-structure-module/anatomy-tables/muscle-tables/muscles-of-the-back-region/) | 肩带、竖脊肌、多裂肌行 | 不把解剖作用直接当成训练激活结论 |
| [UAMS 腹部教学表](https://medicine.uams.edu/neuroscience/education/medical-school-courses/human-structure-module/anatomy-tables/muscle-tables/muscles-of-the-abdominal-region/) | 腹壁肌行 | 腹部压缩与关节运动分开 |
| [OpenStax 2e 8.1](https://openstax.org/books/anatomy-and-physiology-2e/pages/8-1-the-pectoral-girdle)、[8.2](https://openstax.org/books/anatomy-and-physiology-2e/pages/8-2-bones-of-the-upper-limb)、[8.3](https://openstax.org/books/anatomy-and-physiology-2e/pages/8-3-the-pelvic-girdle-and-pelvis)、[8.4](https://openstax.org/books/anatomy-and-physiology-2e/pages/8-4-bones-of-the-lower-limb)、[7.3](https://openstax.org/books/anatomy-and-physiology-2e/pages/7-3-the-vertebral-column) | 骨性标志与脊柱结构 | 学习定位，未建立视频测角阈值 |

截至2026-10-22，OpenStax网页显示CC BY-NC-SA及AI/商业使用许可限制。本库只保存自行组织的中文事实概要及来源定位，未打包原文、教材表格、图谱或插图；来源链接不表示已经取得图谱、商业转载或其他授权。UAMS表格与论文图片同样未复制。后续导入原文/图像应单独核查许可，不能沿用“已核对来源”冒充授权。

## 已实现：主动负重膝触墙、手动墙距

协议ID `wblt-knee-wall-cm`，版本`1`，合并标识`wblt-knee-wall-cm-v1`。单位为**cm**。保持版本1固定语义；更改测量方法、单位、姿势或统计方式时应增加协议版本，不能把不同方法混入同一序列。

主要依据是原始研究 [Konor等，2012，Int J Sports Phys Ther 7(3):279–287，PMID 22666642 / PMCID PMC3362988](https://pmc.ncbi.nlm.nih.gov/articles/PMC3362988/) 的`Methods—Procedures`、`Table 3`和`Discussion`，访问核对日期2026-10-22。研究为20名健康成人，由经过培训的测量者完成单次内复测；不能据此宣称本App无人监督自测、摄像头或长期趋势已验证。

面向稳定墙面，膝沿第二脚趾方向触墙，脚跟全程贴地；调整足墙距离至最远可控触墙位置。尺测大脚趾尖至墙的水平距离，每侧先练习3次、正式测量3次，每次读至0.1cm并保存，代表值取三次均值。可按研究方式每手两指扶墙；App也记录其他支撑方式，但条件不同时不混合比较。开始时10cm仅是研究中采用的起始摆位，不是合格线。

出现任何疼痛立即停止。用户可记录疼痛评分、位置及停止状态，无需凑齐3次；该记录保留在历史中，但不进入趋势。代码未实现临床分流、疼痛诊断或康复处方。

产品规则与研究结论分开：**三次极差超过0.5cm提示复测、暂不进入个人趋势**，这是练伴的重复性筛选约定，未经临床验证，不是研究MDC。0–30cm为输入校验范围，不是正常范围。未完成练习、未确认脚跟贴地/膝触墙/膝沿第二趾方向或出现疼痛的记录也不进入趋势。

## 数据与接口

`backend/mobility.py`提供`router(connection)`，由应用挂载。所有个人数据存储于现有`user_records`，由`database.owner()`限定当前登录账号，随账号数据删除级联清理；无需数据库迁移。

| 接口（均在`/api/mobility`下） | 行为 |
| --- | --- |
| `GET /protocol` | 协议步骤、版本、来源、研究/产品边界与能力状态 |
| `GET/PUT /settings` | 活动度记录保存开关，默认关闭；关闭保留已有记录 |
| `GET/POST /measurements` | 当前账号历史/新增；`request_id`幂等，内容冲突返回409 |
| `GET /summary` | 左右分别返回同条件个人参考、最新均值、跨日期变化和记录点 |
| `PUT /baseline/{left|right}` | 指定本账号、对应侧、满足比较条件的记录为个人参考 |
| `DELETE /measurements/{record_id}` | 删除单条；同步清理该条参考指针 |
| `DELETE /measurements` | 删除本账号所有活动度记录及参考指针 |

每条记录包含协议ID/版本、主动、负重、左右、手动来源、单位、带时区测量时间、每次原始距离及姿势条件、练习完成状态、鞋袜/支撑/场地/热身/尺/测量者/其他条件、疼痛及停止状态。响应保留来源定位与`user_reported_manual_not_clinically_verified`标识。只接受`manual_tape`及`cm`；相机模型/角度/被动测量不能伪装成同一测量。

趋势以最新有效记录的完整条件作为比较组，侧别与协议版本必须相同。默认个人参考为该组首条有效记录，也可手动指定。指定参考与最新条件不一致时明确提示并显示同条件首条；同日重复不计算长期变化。至少存在两个不同日期的同条件有效记录后显示墙距差值；不输出“正常”“异常”“临床改善”“某肌短缩”或自动训练调整。删除后按剩余记录重算。

`mobile/lib/mobility_page.dart`提供独立`MobilityPage(request: FitnessRequest)`：保存授权、可展开的引导/来源、左右/条件/三次读数、疼痛停止流程、个人参考/趋势、历史及单条/全部删除。摄像头测角明确标记为尚未校准开放，模型估计不会进入手动序列。

## 验证

`backend/test_mobility.py`覆盖保存开关、手动来源约束、协议版本、输入与疼痛停止、幂等、三次重复质量、同条件与跨日期比较、左右、手动参考、删除及账号隔离，并验证新解剖图/来源边界。`mobile/test/mobility_test.dart`覆盖三次尺测提交、疼痛立即转停止记录以及显式删除更新历史。没有执行临床或手机相机效度研究；APK只作软件功能交付。
