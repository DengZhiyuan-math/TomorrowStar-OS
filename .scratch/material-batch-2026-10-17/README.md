# 可暂停的多岗位材料批次：实现与验证

对应[票据 07](../gmail-resume-preparation-2026-10-17/issues/07-bounded-batch-orchestration.md)，遵循 `preparation-policy/v1.0`。最终命令、通过数和边界以 [verification.json](verification.json) 为准。

## 实际行为

- 用户明确勾选有限候选后创建暂停批次；创建和页面刷新均不自动开始工作。复用现有 Gmail 读取、完整岗位取源、单岗解释、草稿和独立 PDF 链。
- 最多推进一个岗位。逐岗分析、生成草稿、明确审阅、独立导出，再确认具体 PDF。材料确认后进入 `waiting_application_record` 并暂停；材料完成不能冒充投递、记录完成或整批成功。
- 明确未提交的故障、必需资格缺失或冲突、其他简历语言要求、岗位全文未完成，均保存具体原因和已有进度。其他可处理岗位可以继续；故障岗仅在用户手动重试后恢复，补全文仍用现有取源入口。
- 未知外部结果立即停止推进。取消、更改资格或新建任务不能绕过核验；导出核验只读取原保存回执，绑定当前尝试、输入和草稿。已核验的旧尝试与后续未知尝试分别留存。
- 默认按现有匹配度排序，保留手动调整。逐岗显示匹配分、资格结论、进度和理由，不加 A/B 等级；审核页面保留正确的 JD、资料、草稿、PDF 与审阅版本。
- 暂停、恢复、取消、重复请求、输入 A→B→A、晚返回和重启都保留历史并检查版本；复用同一存储、锁和串行队列，没有第二个执行 worker。

## 证据

- [冻结源码指纹](source-manifest.json)、[本票有界差异](owned-changes.diff)、[最终源码回读](source-readback.json)。
- [保留的既有文件](preserved-baseline.json)：8 个既有测试和 4 个读取／准备链模块保持原字节。工作前的[基线](baseline/)保留。
- [独立审查](review.json)：覆盖未知结果绕过、恢复后未知状态、任务替换及连续两次未知导出；最终无未解决阻断。
- 新增模型／HTTP／浏览器用例验证实际入口、单岗暂停、故障隔离、明确重试、未知核验、集中审核与 Gmail 读取到材料的合成链。日志和 JUnit 文件保存在本目录。
- RED 和失败输出保留原貌。`material-batch-ui-tracer-red.log` 是浏览器启动工具失败；`material-batch-ui-tracer-red-browser.log` 才是缺少批次入口的行为 RED。`material-batch-http-chain.log` 的初次失败来自测试误将版本探测计为模型执行，最终断言只统计实际执行。重启核验的 before-fix 日志是原始失败证据，after-fix 日志是当前复验。
- [PDF 契约](retained-pdf-contract.json)：本票没有修改 PDF 存储、模板或 renderer。此前已验证的两页 A4 合成 PDF 质量证据继续保留；本票的批次 PDF 传输夹具仅验证编排。
- [浏览器启动事件](observed-browser-startup-failure.json)：本轮首次沙箱启动测试 Chrome 触发用户所贴崩溃；后续采用已获批准的隔离浏览器运行。此事件不证明历史故障或安装版已修复。
- [票据回读](tracker-readback.json)与[本地链接核验](document-links.json)。

## 验收范围

源码与隔离合成验证。没有读取私人资料或真实邮箱、调用真实模型／岗位／ATS、上传或 Submit，没有恢复旧申请、启动或替换安装版 App、提交 Git 或写远端。真实申请继续暂停。安装、真实试用和真实简历人审仍需各自的后继验收。
