# 食物库与动作库

食物库位于“饮食”模块，可点击“打开食物库”或该页右上角餐具图标进入。动作库位于“训练计划 / AI 陪训”，可点击右上角动作库图标或“浏览动作分类”进入。两者为独立页面，没有互相切换的标签。各自支持搜索、分类、详情、新增、编辑、停用、JSON批量导入及复制导出。选择“用于饮食/训练记录”会回到对应页面。

## 食物

初始44条：40条USDA FoodData Central SR Legacy数据中文映射 + 4条原MVP示例。包含谷物薯类、肉蛋鱼、乳制品、豆类、蔬菜、水果、坚果与油脂。

营养统一按**每100克可食部分**：kcal、蛋白质g、脂肪g、碳水g；标记生/熟/成品，保留FDC编号、英文原名和来源。USDA条目是美国通用食材参考，中文名称由项目翻译，不等同于特定国产品牌或所有烹饪方式。SR Legacy为2018年的历史最终版本，并非实时更新数据。原4条示例明确标记未核验。

自定义食物按包装标签或可靠资料录入来源；若标签按每份、每100毫升或kJ计，先换算到每100克与kcal后录入。修改或停用食物不会重新计算历史饮食：每条餐食保存名称、状态、来源及营养快照。

官方下载：https://fdc.nal.usda.gov/download-datasets/ 。数据溯源清单：`backend/data/food_sources.json`。

复现基础数据：下载官方SR Legacy CSV 2018-04并解压，再运行：

```powershell
.\.venv\Scripts\python.exe scripts\build_food_seed.py 'CSV文件所在目录'
```

## 动作

初始38条：31个负重动作与7个自重资料条目。按18类关节动作模式分类，附部位、关节动作、主要/辅助肌群、器械、难度、变式、重量口径与检测能力。详见 `docs/MOVEMENT_CONTENT.md`。

- 负重动作可用于计划、RM及训练记录，AI生成使用当前有效负重动作库。
- 自重动作当前只浏览资料；计次/时长与负重记录口径不同，后续在独立模块实现。
- 只有bench、squat、deadlift有现有实验性实时计次。新增其他动作不启用检测，核心三项的身份与拍摄定义固定；教学文案可以编辑，并共同用于AI参考。
- 高杠与低杠深蹲、传统与罗马尼亚硬拉是不同ID，RM不相互套用。
- 已有动作的类型、器械和重量口径不可改变；变化时新建变式，避免旧RM被用于不同单位或器械。
- 动作说明是项目分类内容，现有教学草稿、原创示意GIF及纠错规则尚未完成审核，不冒充书籍逐页验证内容。

## 存储与接口

SQLite新增`catalog_items`表，按kind与id唯一。启动使用`INSERT OR IGNORE`导入基础数据，已有编辑和停用不会被重置。停用保留条目和历史记录；当前管理权限沿用单用户本地开发模式。

兼容旧手机客户端：默认`GET /api/catalog`只返回已有实时检测的动作，避免旧版客户端把新动作交给三项检测器。新版Flutter与浏览器预览请求`/api/catalog?extended=true`获取完整动作库；资料库分页接口始终返回符合筛选条件的全部条目。

| 接口 | 用途 |
|---|---|
| GET /api/library/foods 或 exercises | q关键词、category关节动作/食物类型、body_part训练部位、type训练类型、limit/offset分页 |
| GET /api/library/{kind}/{id} | 条目详情 |
| POST /api/library/foods 或 exercises | 新增条目 |
| PUT /api/library/{kind}/{id} | 编辑条目 |
| DELETE /api/library/{kind}/{id} | 停用 |
| GET /api/library/{kind}/export | 导出完整JSON |
| POST /api/library/{kind}/import | 导入JSON数组，一次1–500条 |

导入在事务中执行，不覆盖已有ID；重复或无效数据会整批失败。导出库包含原ID，向同一个库再次导入会提示冲突；如需新增副本，先去掉或修改ID。导入的来源及能力标记按用户录入处理，不允许导入数据自行宣称已审核或启用实时算法。

食物导入示例：

```json
[{"name":"我的酸奶","category":"乳制品","state":"prepared","kcal":100,"protein":8,"fat":4,"carbs":8,"source_label":"包装每100克营养标签"}]
```

动作导入示例：

```json
[{"name":"我的器械划船","category":"背部","type":"weighted","equipment":"坐姿划船机","weight_basis":"器械显示重量；保持相同器械","source_label":"用户维护的动作分类"}]
```
