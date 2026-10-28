# M2 取消职责与编辑停止门槛

本记录只覆盖此子项，不宣称 M2、T09 或全部 Module 迁移完成。没有真实模型调用、真实
申请、页面写入工具或安装更新。

## 实际交付

- `Flow.cancel_preparation` 只停止准备。`Flow.cancel` 为同语义兼容别名；不再调用 Worker。
- `Pipeline.cancel_current` 和 `request("cancel-current", ...)` 协调 Worker 条件取消和 Flow
  准备取消。原当前岗不变；持久记录两部分的实际结果，部分失败不报告全部成功。
- Worker 控制调用在应用锁之外；固定 task/application/batch/run 由 Worker 公开
  `cancel_execution` / `cancellation_progress` 核对，Pipeline 不解释 intent 或 native 状态。
- 停止已确认时不重发控制。Codex 工具尚未排空时保留 stopping；tick 只核对结果，确认后
  更新取消结论，不需要用户再次请求。未知页面效果继续 unknown。
- Worker 已发布而 Flow 引用保存失败时，Flow 只消费已核对的 cancellation 交付来补原
  pending 引用；不覆盖已有引用，不把未知页面效果当作完成。
- 两处材料编辑准入均消费 Worker 的 `assistance_stop_pending`：暂停不代表工具排空。
  stopping/unknown 均等待；可靠停止后可编辑，旧材料和原写者占用仍保留。

父任务已将旧 `/api/flow/cancel` 接到 Pipeline，并保留旧 Task JSON，加上实际 cancellation
投影；旧返回的 Flow.status=cancelled 仅代表准备状态。

## 验证

- 新增 Pipeline 取消用例 9 项，编辑停止门槛用例 4 项。
- 相关既有组合：`m2-final-targeted.log`，**220 passed**。
- 本批冻结后新用例及父任务 HTTP 接线：`frozen-new-tests.log`，**15 passed**。
- 7 个拥有/联动文件的 Ruff 和格式检查通过。
- 原 Flow 取消回归更新为纯准备语义；独有的发布后引用保存失败故障已由新 Pipeline
  公共 Interface + 真实 WorkerService + 真实 Flow 路径覆盖，未删除该场景。

保留了 RED→GREEN 日志：缺少 Interface、编辑门槛、异步排空核对、部分失败重试、
取消后 Continue、旧执行批次及失败停止交付等。测试均使用合成临时工作区。

## 后续 journal 与求职信所属提交

后续迁移和验证已完成，见 [journal-owners.md](journal-owners.md)：22 项新增，相关组合
116 passed、6 deselected。原 journal、普通严格核验、人工内容与历史保持；三方 preflight
先于第一个参与方保存，未新增事务框架或模型调用。

## 后续范围

T09 完整编辑前协调、其他准备内部协调的所属收拢、M1 Worker 绑定读取迁移，
以及父任务的完整默认套件与隔离浏览器审计仍需分别完成。本记录不代替它们。
