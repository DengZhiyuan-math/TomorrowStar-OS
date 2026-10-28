# 跨岗位简历复用规划导航

2026-10-19 规划结案：八张决策票已完成，地图closed／implementation-ready-plan-only。[最后一票](issues/08-integration-handoff.md)持有首版接口、记录及验证交接。当前没有开放子票或待用户决定的产品问题；尚未实现、安装或实测提速。后续实施先做原PDF直接复用，收益证实后再补局部修改加速，不增加用户操作。

## 初始建图导航（历史）

规范入口：[规划跨岗位旧简历检索与自动复用](map.md)。此图止于规格，不是功能交付图。所有子票本次保持open／none；实际状态以子票为准。

本轮用户已确认自动选定、说明理由及允许切换；新增经历触发重评并优先更新。其余产品选择通过决策票逐题完成，不把建议当作既定规格。

## 阅读与顺序

- 先读地图Destination与Notes，再查实时前沿；按需查[代码勘查](current-state.md)。
- 初始两张无技术依赖的票为[厘清三种判断与自动选定的语义](issues/01-score-and-selection-semantics.md)及[确定哪些历史简历有资格进入候选库](issues/02-candidate-pool-and-lineage.md)，均须用户参与。
- 三种判断澄清后讨论[岗位比较与召回](issues/03-job-comparison-and-retrieval.md)；与候选资格共同解锁[三种处理方式的分界](issues/04-three-way-decision.md)，之后确定[新增经历及审核继承](issues/05-validity-and-review-inheritance.md)、[交互原型](issues/06-selection-experience.md)、[校准与验收](issues/07-calibration-and-acceptance.md)，最终形成[实现交接](issues/08-integration-handoff.md)。
- 需要外部事实后再新增research票并按Wayfinder派研究子代理；当前问题来自已有本地接口和产品偏好，不为了票型而编造外部研究。

## Wayfinding operations

本地Markdown为tracker，无原生blocking；子票路径为身份，Parent指向map，Blocked by使用标题相对链接。先创建全部票，再连接依赖。规范操作沿用[既有材料图](../gmail-resume-preparation-2026-10-17/README.md#wayfinding-operations)。

领取前必须满足Status=open、Assignee=none、全部直接前置closed/resolved且非行政superseded。先写唯一Assignee；HITL须实际用户参与，不能机械就绪就自动代答。每会话最多解决一张非research票。建图会话不解决任何票。

从仓库根目录读取实时全量查询：

```sh
uv run --locked --offline --no-sync python -B scripts/query_tickets.py --json
```

在tickets数组按path前缀`.scratch/cross-job-resume-reuse-2026-10-19/issues/`筛选。本图会进入全仓口径，不加入旧正式23票或旧两线交付口径。未知与错误保留，查询不授予外部执行许可。

## 建图验证 — 2026-10-19

使用现有`query_tickets.query`只读核对：全仓实体票由109增至117，本图8票均open／Assignee none；依赖无错误、无环，初始机械前沿为上述两票，均HITL。原20项元数据警告数量保持，不自动补写未知值。

逐一比较建图前记录的109张旧子票SHA-256，均未改变。新图全部Markdown本地链接存在；README的`git diff --check`与新图空白检查通过。仅修改规划和根导航，未运行业务测试，也未变更业务代码或私人记录。
