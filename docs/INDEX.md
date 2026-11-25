# 文档索引与适用版本

索引更新：2026-11-02。当前业务代码0.5.1；各模块验收与已上线状态单独记录。建议按职责读取，不需要新会话一次读完所有历史资料。

## 当前入口

| 文档 | 职责 |
|---|---|
| [PRD](PRD.md) | 用户目标、产品规则、功能ID和验收条件；不是完成声明 |
| [架构与AI](ARCHITECTURE_AND_AI.md) | 当前代码结构、模型工具、提示词、数据与部署边界 |
| [开发状态](DEV_STATUS.md) | 已实现/已验证/已部署差异、失败记录、P0/P1工作队列 |
| [新会话交接](DEVELOPMENT_HANDOFF.md) | 同目录接手、环境、测试/构建、云端注意事项及开场文本 |
| [路线图](ROADMAP.md) | 当前任务优先级入口；详细状态统一在DEV_STATUS |

## 0.5 / 0.5.1 专项

| 文档 | 内容 |
|---|---|
| [EXERCISE_SELECTION](EXERCISE_SELECTION.md) | 默认97项日常动作清单、筛选依据和历史兼容 |
| [EXERCISE_CATALOG_IMPORT](EXERCISE_CATALOG_IMPORT.md) | 1579条完整目录、32类关节标签、302套许可演示、来源映射与未审核边界 |
| [TRAINING_EXECUTION](TRAINING_EXECUTION.md) | 逐组记录、冻结目标、交替组、目标/实际对照、趋势、个人进阶设置、译文与外部食品 |
| [LIVE_EVALUATION](LIVE_EVALUATION.md) | 伴练逐次证据、拒判、本机轨迹授权、合成回放与独立双人计次标注/批量评测 |
| [EXECUTABLE_CYCLES](EXECUTABLE_CYCLES.md) | 周期结构、紧凑蓝图、恢复周、完成度、编辑与确认操作 |
| [TRAINING_PROGRAMS](TRAINING_PROGRAMS.md) | 画像分化/训练法偏好、每日目标、按天展示、协议组次与编辑/进阶一致性 |
| [NUTRITION_RULES](NUTRITION_RULES.md) | 确定性营养目标、证据与产品策略、校准资格与失效 |
| [ANATOMY_MOBILITY](ANATOMY_MOBILITY.md) | v2解剖扩充、骨性标志与手动膝触墙试点 |
| [KNOWLEDGE_RETRIEVAL_EVALUATION](KNOWLEDGE_RETRIEVAL_EVALUATION.md) | 混合检索、80问相关性与46问回答/引用评测及发布绑定 |
| [KNOWLEDGE_UPGRADE_STATUS](KNOWLEDGE_UPGRADE_STATUS.md) | 首轮失败和性能指标；SOTA能力边界与待验收项 |
| [REDIS_CACHE](REDIS_CACHE.md) | 提示词/训练记忆/知识缓存、事务失效与撤权、开发 Redis 安装、状态与性能口径 |
| [AGENT_ROUTING](AGENT_ROUTING.md) | 健康/计划/饮食等分层路由、Jev/OpenAI原生决策、语义后备、工具/上下文和恢复约束 |
| [PRIVACY_LIFECYCLE](PRIVACY_LIFECYCLE.md) | 撤权/删除/更正后的AI衍生内容清理、并发防回灌、确认目标保留、客户端刷新及边界 |
| [POSTGRES_ACCEPTANCE](POSTGRES_ACCEPTANCE.md) | 临时物理PG集群、迁移、最小权限、全量业务及备份恢复；破坏性fixture安全校验 |

## 仍有用的模块说明

以下文件部分保留早期实现背景。当前完成状态和需求冲突以PRD、当前架构及DEV_STATUS核实。

| 主题 | 文档 |
|---|---|
| Agent / 研究基础 | [AGENT_AND_RESEARCH](AGENT_AND_RESEARCH.md)、[FOUNDATION_KNOWLEDGE](FOUNDATION_KNOWLEDGE.md)；0.3/0.4历史基线，不代替0.5状态 |
| 画像、训练、RM、计划 | [AI_COACH](AI_COACH.md)、[AI_PLANS](AI_PLANS.md)、[STRENGTH_PROFILE](STRENGTH_PROFILE.md)、[TRAINING_MEMORY](TRAINING_MEMORY.md)、[RM_ASSESSMENT](RM_ASSESSMENT.md) |
| 动作与实时 | [MOVEMENT_CONTENT](MOVEMENT_CONTENT.md)、[REALTIME_COACHING](REALTIME_COACHING.md)、[STARTING_STRENGTH_RULES](STARTING_STRENGTH_RULES.md)；旧38条说明已被完整目录扩充 |
| 公共资料库 | [LIBRARIES](LIBRARIES.md)；基本CRUD仍有参考价值，动作总量以新导入文档为准 |
| UI / 教练 / 提醒 | [UI_REDESIGN](UI_REDESIGN.md)（含2026-10-25 Taste核心UI与验收）、[COACH_PERSONAS](COACH_PERSONAS.md)、[COACH_REMINDERS](COACH_REMINDERS.md)、[COACH_ART](COACH_ART.md)、[BRANDING](BRANDING.md) |
| 账号与数据库 | [AUTH_AND_DATABASE_DESIGN](AUTH_AND_DATABASE_DESIGN.md)、[LOGIN_SETUP](LOGIN_SETUP.md) |
| 部署与私有手机测试 | [DEPLOY_HUAWEI](DEPLOY_HUAWEI.md)、[PRIVATE_MOBILE_TEST](PRIVATE_MOBILE_TEST.md)、[DOMAIN_SETUP](DOMAIN_SETUP.md)；历史0.1/0.2包信息不能当最新版本 |
| Android / 签名 / 备案 | [ANDROID_DEBUG](ANDROID_DEBUG.md)、[ANDROID_SIGNING](ANDROID_SIGNING.md)、[APP_FILING_CHECKLIST](APP_FILING_CHECKLIST.md)；签名身份保留，合规/平台配置需按实际情况核验 |

## 历史归档

- [旧架构说明](history/ARCHITECTURE_PRE_0_5.md)：含0.2流程和早期附录，部分架构结论已过时。
- [旧README](history/README_PRE_HANDOFF.md)：保留原启动/交付背景，不能据其38条动作、固定活动系数等旧描述开发。
- [旧路线图](history/ROADMAP_PRE_HANDOFF.md)：包含尚未Agent化、计划只由用户手定等旧方向。

## 维护规则

- 改产品规则时更新PRD及专项说明；改结构/提示词/数据流时更新架构；每轮验收/交付更新DEV_STATUS。
- 测试报告需要写实际运行范围、版本和日期；失败、跳过和未测试分开，历史成绩不挪用。
- `.tools`中的回执用于本机诊断，Git/新机器不一定有。可重建命令和关键结果需留在文档，凭据和私有记录不留。
- 这里是人工维护文档体系，没有自动保证代码与文档一致；新会话仍要核对git diff和相关源码。
