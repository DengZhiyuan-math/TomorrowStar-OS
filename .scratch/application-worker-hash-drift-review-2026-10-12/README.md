# 9 个未封存文件的来源与影响核查

来源已确认：同一工作区的聊天“增加投递前岗位筛选”，thread ID `01a13058-2b28-7850-a17b-04053a28c810`。15 个已完成文件写入记录覆盖全部 9 个路径，写入发生在 2026-10-12 13:44:35–13:54:26 UTC；另有 5 个已完成格式化命令记录。改动用于岗位批量/人工精准分流、评价字段、API/UI 和合成测试。9 个文件均为 Git 未跟踪文件；本核查依据完成的任务记录归因，没有可引用的提交。

在新证据目录内重构的 9 份变更前文件，SHA256 全部精确匹配原审查基线。实际工作区未回写。[来源事件](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-hash-drift-review-2026-10-12/source-file-events.json>)、[格式化事件](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-hash-drift-review-2026-10-12/source-format-events-final.json>)与[旧哈希复原结果](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-hash-drift-review-2026-10-12/reconstruction-final-result.json>)组成取证链。

| 文件及逐项差异 | 改动内容 | 列入历史原生输入 |
| --- | --- | --- |
| [application_worker.py](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-hash-drift-review-2026-10-12/diffs/src/career_evidence_graph/application_worker.py.diff>) | `_prepare` 增加 batch/precision、单岗位复核、live 分流守卫和 workflow 元数据 | 是 |
| [career_portal_data.py](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-hash-drift-review-2026-10-12/diffs/src/career_evidence_graph/career_portal_data.py.diff>) | 增加 6 类岗位评价/分流字段、策略备注解析和枚举校验 | 是 |
| [career_portal.py](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-hash-drift-review-2026-10-12/diffs/src/career_evidence_graph/career_portal.py.diff>) | 准备入口核对分流；读取、创建和更新响应保留 screening | 否 |
| [worker.js](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-hash-drift-review-2026-10-12/diffs/src/career_evidence_graph/portal_static/worker.js.diff>) | 批量按钮、单岗位精准准备和 workflow 展示 | 否 |
| [test_ashby_drafts.py](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-hash-drift-review-2026-10-12/diffs/tests/test_ashby_drafts.py.diff>) | 合成 fixture 显式设为 batch | 否 |
| [test_hosted_ats.py](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-hash-drift-review-2026-10-12/diffs/tests/test_hosted_ats.py.diff>) | 合成 fixture 显式设为 batch | 否 |
| [test_generic_worker.py](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-hash-drift-review-2026-10-12/diffs/tests/test_generic_worker.py.diff>) | 合成 fixture 显式设为 batch | 否 |
| [test_career_portal_http.py](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-hash-drift-review-2026-10-12/diffs/tests/test_career_portal_http.py.diff>) | batch fixture、准备守卫及保存后 screening 响应回归 | 否 |
| [application-worker-workflow.md](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-hash-drift-review-2026-10-12/diffs/docs/application-worker-workflow.md.diff>) | 更新筛选与分流说明 | 否 |

“否”只表示该文件未列入原生 invocation 的输入清单，不表示新投递功能已验证。完整 SHA256 和四阶段比较见 [哈希比较](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-hash-drift-review-2026-10-12/four-stage-hash-comparison.json>)。career_portal.py 与 test_career_portal_http.py 在第一次漂移记录之后又由同一聊天更新；两次更新已进入上一轮完成回执。本轮当前 9 个哈希全部匹配该完成回执，未发现新的漂移。

## 对 finalization-fix 审查的影响

固定入口仍为 SHA256 `b0473c4e226de2b35b1d94031a82fc4e53a31362167ac8ea50d84f6f3bb7784d`，其 282 个 manifest 成员有效。目录身份绑定、归档写入、最终输入核验、完整 result 写入后的清理、描述符关闭与 cwd 恢复实现均未变化。

| 结论 | 本轮评估 |
| --- | --- |
| Standards：0 规范违规，0 启发式问题 | 对固定封存包的结论保留 |
| Spec：0 发现 | 对固定封存包的结论保留 |
| 14 个 Standards 场景、33 个 Spec 场景、280 项副本回归 | 原执行源码、输入、日志和结果均保留；本轮未重跑 |
| 当前工作区的投递分流功能与原生兼容性 | 未执行验证；不扩展上述结论 |

独立探针替换 `run_checkout` 为合成归档生产器；副本回归也使用合成输入。它们验证最终化和目录契约，不验证新的 worker 准备流程。新增 worker 改动只位于 `_prepare`；WorkerStore AST 未变。实际原生 current pump 来自 application_worker_browser.py，该文件原 SHA256 仍匹配，ApplicationRunner.pump 未变化。这是静态核对，不证明当前完整运行一定通过。见 [定义影响](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-hash-drift-review-2026-10-12/static-definition-impact.json>)与[评估结果](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-hash-drift-review-2026-10-12/impact-result-final.json>)。

## 对历史原生证据的影响

只读核对 17 个带 invocation 的封存原生归档实例。每个实例的当前绑定均因 application_worker.py 和 career_portal_data.py 改变而失配。已有归档字节、结果和可用 ZIP trace 的 CRC 保持原样。finalization-fix 自身的两个归档仍记录矩阵 26 项通过、红测 1 项预期失败，27 份 raw facts 与 4 份 trace 可复读。

7 个早期归档另有 rerun.py 版本差异；这些差异在原审查基线中已存在，未归因于本轮 9 个文件。3 个早期归档的 child-artifacts facts 集合为空；空集合标为未观察，不当作事实对应通过。历史 default 矩阵的 3 项失败、其他红测失败及缺失原件集合均保持原状态，不升级为完整通过。逐实例记录见 [原生影响明细](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-hash-drift-review-2026-10-12/historical-native-impact-final.json>)。实例数不等于新增运行数，本轮新增原生运行为 0。

历史结果仍能证明其记录输入下的合成观察。它们不能验证当前工作区。若今后需要验证当前版本，应另建绑定当前输入的新运行证据，保留历史封存包。此次来源定位不识别历史 TargetClosedError 的发起者，也不验证生产恢复。

## 保留与执行边界

[本轮保留核对](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-hash-drift-review-2026-10-12/preservation-final.json>)：3740 个本轮起始公共哈希全部未变；16 个封存目录的文件集、完整树和链接目标未变，包括 14 个旧包及前次审查/补充包。前次审查的完整外置封存清单仍有效，原漏项和失败记录未修改。私有原字节/元数据、私有诊断包不变；04、06 均保持 closed。私有检查只保留聚合结果。9 个相对更早基线的差异保持原样。

只新增本目录与包外回执。未运行 worker、pytest、浏览器、ATS 或模型；未发送其他聊天消息，未提交或回写工作区。代码解析、哈希与 ZIP 检查均使用标准库。生产恢复未验证。

捕获首轮错误、标准 patch 首轮未匹配/自动反向的结果，以及首轮空格式化事件提取均保留。最终重构只修改本目录的证据副本，以 9 个原 SHA256 精确匹配为门槛。最终评估对空 facts 集合使用 null；首轮记录保留，以上结论使用 `*-final.json`。执行源码快照也保留。封存后仅运行 postseal_check.py；捕获和重构应在新的证据目录进行。

完成回执：[封存后只读回执](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-hash-drift-review-postseal-check-2026-10-12.json>)。
