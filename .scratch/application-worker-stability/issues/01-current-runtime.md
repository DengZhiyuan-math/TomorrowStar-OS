# 01: 区分当前运行与历史检查点

**What to build:** 用户在工作台能区分当前运行、历史检查点、观察过期和已确认退出，并知道本次运行加载的版本。

**Blocked by:** None (can start immediately).

**Status:** closed

**Parent:** [确定故障隔离、恢复保证与诊断验收标准](../../application-worker-next-stage/issues/02-recovery-contract.md)。

**Specification:** [稳定性阶段：故障隔离、恢复保证与验收规格](../../application-worker-next-stage/assets/stability-contract.md)。

- [x] 当前运行具备独立身份、启动版本和观察时间；磁盘代码变化不能把旧进程标成新版本。
- [x] 状态读取与工作台展示一致；过期心跳和旧 PID 不被解释成实时页面或已确认退出。
- [x] 当前受管进程的退出码与无法判断的历史退出分开；未知原因保持未知。
- [x] 合法旧检查点仍可读取；损坏记录不被静默修复或覆盖；页面历史明确标注来源。
- [x] 重复启动被现有单实例机制拒绝，原运行与页面不受影响。
- [x] 对应 T10、T17 的存储、API、工作台和进程检查通过。诊断时限按已确认规格验证。

## 共同边界

- [x] 每票均保持自动最终 Submit 动作和最终请求放行数为零。
- [x] 测试使用隔离合成页面与临时记录；真实岗位不用于反复故障保存或上传。
- [x] 复用现有 worker、答案库、原记录、单实例机制、原生控件与草稿契约；不新增独立浏览器进程或平台队列。
- [x] 个人资料、答案、简历、认证和真实 trace 保持私有；公开验收报告只含合成证据。
- [x] 完成每票时即有自己的演示与测试，不把测试全部推迟到最后一票。

## 执行与验收记录

2026-10-11：已实现启动 run 身份与源码清单、历史 run 保留、6 秒观察过期、受管 child 退出码与历史 unknown 分离，以及工作台同源展示。

- 离线：`tests/test_worker_stability.py tests/test_application_worker.py`，29 passed。
- 原生进程 / 工作台：`test_lever_worker_browser.py -k "conflict_single or workbench"`，2 passed。单实例冲突返回 3；原 worker 保留。
- 首次沙盒原生运行：2 failed，Chromium MachPort 启动权限错误。允许本机浏览器环境重跑通过。首次重跑中的恢复提示兼容问题已修正，保留原失败输出。
- 自动 Submit 与最终请求放行：0。仅隔离合成数据，无真实 ATS 或模型调用。
- 完整阶段回归与更细故障时限证据由 06 汇总；本票不声明真实休眠或真实申请验收。

阶段最终结果与源码绑定见[阶段整体验收](../evidence/acceptance.md)。
