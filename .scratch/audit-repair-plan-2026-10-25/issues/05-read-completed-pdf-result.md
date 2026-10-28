# R05：接通原编译结果的只读取回

Type: bug
Label: wayfinder:task
Status: closed
Priority: P2
Interaction: AFK
Assignee: Codex / pdf_repairs
Created: 2026-10-25
Parent: [审计修复计划](../map.md)
Blocked by: 无
Triage: verified

## 已确认问题

审计身份：M1。编译成功但响应丢失时，生产重查仅查本地文件，即使原服务有精确已完成结果也无法采用。
证据以[原审计报告](../../work-audit-2026-10-25/README.md)为准，原实验补丁已撤回。

## 文件所有权与最小范围

`application_worker.py` 的文件重查；复用 `application_cover_letter.py` 的现有读取 Interface。新增独立 Worker readback 测试；既有 delivery 测试局部协调。

保留 `read_cover_letter_pdf` 的完整本地零写入／零网络路径；仅回执不完整时消费现有 `reconcile_cover_letter_pdf` → `read_compiled`。不重编译、不重写正文、不重放模型。

## 验收条件

- [x] 完整本地回执直接采用，零网络、零新写入；即使 export.json 补写持续失败，也不能破坏原本可读的本地成功路径。
- [x] 编译完成、响应丢失时取回同一原尝试的准确结果；全程编译和模型调用次数不增加。
- [x] 未完成、不可读、正文／模板／源版本不符、PDF hash／格式／页数不符及读取期间源漂移保持等待或原明确错误，不伪造 ready。
- [x] 原暂停／当前岗、未知网页动作、人工编辑与来源检查保持；重复 request_id 幂等，旧回执和历史保留。
- [x] 所有编译与读取客户端均显式使用替身，离线回归不能连接真实 Prism。

## 状态与执行范围

建票时只规划、未领取、未实施；后续用户调用 implement 授权执行。技术前置依赖为无；共享文件由同一负责人串行集成。
实施时先补当前版本的失败回归，再验证最小修复。不能直接把已撤回的实验补丁或其绿测当成当前交付。
不改真实私人配置／材料，不运行真实模型、Prism 或 ATS，不更新 App；最终 Submit 保持手动。

## 本轮实施与验证（2026-10-25）

- `application_worker.py` 保留 `read_cover_letter_pdf` 本地只读快路径，仅在 `letter_export_needs_recheck` 时使用已有 `reconcile_cover_letter_pdf` 与显式配置的客户端读回原结果，不编译或重放模型。
- 完整本地回执测试持续模拟 export.json 补写失败，仍可成功采用；构建目录原字节与 mtime 均不变，网络读取为零。旧未完成用例现在也显式注入只读替身客户端。
- 新增 `test_cover_letter_worker_readback.py` 36 项公共 Worker 回归。首个成功读回反例在修复前失败；修复后覆盖原完成结果、重复／冲突 request_id、实际依赖策略、未完成／不可读、正文／模板／源／PDF hash／格式／页数及读取期间源漂移，还有暂停、当前岗、未知动作及人工编辑守卫。
- 组合例先证明 image/* 必需字段零编译，再以同一人工正文改为合法 PDF 字段，模拟一次编译完成但响应丢失，仅一次只读结果查询，保留旧回执与正文。
- 受影响回归：168 passed、13 deselected。日志 `/private/tmp/tomorrowstar-audit-repairs-2026-10-25/r04-r05/`；最终组合回归和独立复审由 R07 记录。
- 所有实际编译／读取接口均使用合成替身，没有连接真实 Prism、模型、ATS，没有 App 更新、提交或发布。

### 独立复审后的完整性修正

独立复审发现，新接通的回读路径会在原有 reconcile 辅助接口中覆盖指向私人文件的 PDF 符号链接，或覆盖存在但 hash 冲突的本地 PDF。已先补 13 项公共入口反例（11 failed、2 passed），再收紧同一辅助接口：完整 PDF/build 对验证失败时保持等待；读取前后检查输出及祖先符号链接；全部已有 PDF/build/export 证据必须与原结果一致，才可补齐缺失部分。缺失 PDF 使用独占创建，已有一致的 PDF/build 原字节与 mtime 不变。最终定向结果为 168 passed、13 deselected；旧绿测已被本次结果取代，仍须 R07 最终冻结回归及复审。

## 最终收尾 — 2026-10-25

本票通过本轮源码验证及独立复审，随 R07 关闭。最终版本、组合回归、安装差异及真实验收边界见[实施与交接](../implementation.md)与[机器摘要](../verification.json)。原规划段落及中间状态保留为历史。
