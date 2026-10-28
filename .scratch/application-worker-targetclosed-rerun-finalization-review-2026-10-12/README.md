# finalization-fix 独立审查 — 2026-10-12

Standards：0 项规范违规，0 项可操作启发式问题。Spec：0 项发现。未发现本次变更缺失要求、范围扩张或错误实现。两轴独立设计探针并形成结论；未根据另一轴结果修改判断。

固定基准为封存 subdirs-fix `rerun.py`，SHA256 `12c11c5eb9b1331bd46bb276b748f402fcc17174c59b21431f78b747ac4f3e76`。目标为封存 finalization-fix `rerun.py`，SHA256 `b0473c4e226de2b35b1d94031a82fc4e53a31362167ac8ea50d84f6f3bb7784d`。目标 manifest SHA256 `f056721ec94db5558cdff44ecaf8c079c18495f8ee3b23c6523089202e6b6435`，282 个成员有效。Git HEAD 仅作元数据；commits 为空，审查对象是封存包之间的差异。

[范围](review-scope.json)、[完整差异](review.diff)与[请求](request.md)固定输入。规格来自源包 request.md/README.md。规范来自 AGENTS、README、CONVENTIONS、ARCHITECTURE、PROJECT 和数据边界。缺少 docs/agents/issue-tracker.md 的远程 tracker 配置；本次使用用户明确给出的本地请求和封存谱系。

| 检查 | 最终结果 |
| --- | --- |
| Standards 独立新入口 | 14/14 通过；旧入口 2/14 通过、12 项预期不通过 |
| Spec 独立唯一场景 | 33/33 新入口通过；同 33 场景的旧入口 11/33 通过 |
| Spec 对照性质 | 16 项外部原件被提前删除/定位失效；6 项成功场景清理顺序违反 |
| Spec 目录 FD 账本 | 新 636 代、旧 732 代全部关闭；合计 1368，不将其写为新入口数量 |
| FD/cwd 与合成保护根 | 两轴各自验证；均关闭、恢复，完整保护树、链接与字节不变 |
| 既有回归副本 | 280 passed；0 failure/error/skipped |
| 实际封存源 CLI | 56/56 拒绝；14 根 × 正常/大写 × 空/重复前缀 |
| 旧公共证据初次核对 | 3637 个哈希全部不变 |
| 旧公共证据末尾核对 | 3637 个已核对；3628 不变；9 个未封存工作区文件变化 |
| 封存包 | 14 个包的哈希、文件集、完整树与链接目标不变 |
| 私有证据 | 原字节/元数据与私有诊断包不变；只输出聚合结果 |
| 工单 | 04 closed；06 closed |
| 新浏览器/ATS/模型调用 | 0 |
| 生产恢复 | 未验证 |

独立探针确认：输入读取异常、不匹配及 result 的独占打开、write、flush、close 异常均不触发清理。实际外部 facts、trace、XML 和缓存保留；temporary-workspace.json 的路径仍存在，owner_pid/synthetic 正确。成功场景先读取完整 JSON，再调用真实 rmtree。完成的 pytest 0/1/2 都按最终化门槛处理。suite/archive 异常及 cached cases、child-artifacts、pytest-cache 的路径替换也覆盖。

失败探针的 /tmp 原件继续保留。Standards 保存新入口 11 个保留场景；Spec 最终保存 27 个保留场景。每轴的首轮和最终结果不累加。基准外部 staging 被提前删除不代表归档原始字节全部丢失；本审查对照针对新增的外部原件保留契约。

副本只在本新审查目录运行。复制入口增加被审源包的保护根；精确集合断言相应增加一项。清理和目录绑定实现不变，其余副本字节一致。哈希及差异见 [副本审计](regression-copy/audit.json)、[隔离差异](regression-copy/isolation.diff)，执行源码快照、[日志](regression-copy/offline.log)与[XML](regression-copy/offline.xml)均保留。封存后不要在此目录复跑离线测试，旧 TMPDIR 反例会在源码副本目录临时创建子目录。

已有原生归档保持原字节：26 项矩阵通过、历史红测保留 1 项预期失败；27 raw facts、4 native traces 的事实对应、CRC 和外部完整复制通过。源包 3 份最终化失败见证的定位和外部字节仍有效。本次未新增浏览器运行。[初次源包封存复读](source-postseal-replay.json)中当前输入绑定为 true；末尾因未封存工作区变化，[只读原生核对](native-readonly-final.json)中两套归档的当前输入绑定均为 false。不能把历史原生结果用于验证变化后的工作区。

## Standards

**Conclusion: 0 documented-standard violations; 0 actionable heuristic findings.** All 12 hunks in 8 files were reviewed against the fixed sealed-package comparison. No Spec report was read.

| Successor hunk | Documented standards assessment | Heuristic assessment |
| --- | --- | --- |
| `rerun.py` +29 | Adding the two predecessor roots preserves sealed evidence (`CONVENTIONS.md:19–20`). | Concrete protection requirement; no speculative abstraction. |
| `rerun.py` +424 | Removing premature cleanup preserves failed-run originals (`CONVENTIONS.md:43–45`). | Small local change. |
| `rerun.py` +433 | Existing hash comparison and writer now gate existing stdlib cleanup (`AGENTS.md:10–14`; `CONVENTIONS.md:11–15`). | No duplicate validator or new abstraction. |
| `test_sealed_parent.py` +69 | Mirrors concrete protected packages. | Existing fixture reused. |
| `verify_preservation.py` +37 | Advances the predecessor audit chain; exposes aggregate results (`docs/data-boundaries.md:21–23,65–68`). | Existing audit reused. |
| `postseal_check.py` +36 | Updates the actual rejection count. | No finding. |
| `postseal_check.py` +56 | Checks retained synthetic originals and locators. | Fixed byte checks support independent witness verification. |
| `postseal_check.py` +92 | Adds the witness results and retains the production limitation. | No finding. |
| `README.md` +1 | Separates finalization, failed evidence and production acceptance (`CONVENTIONS.md:6–7,43–48`). | No finding. |
| `request.md` +1 | Records the bounded successor scope. | No finding. |
| `test_finalization.py` +1 | Adds invariant regressions in synthetic temporary workspaces (`CONVENTIONS.md:21–22,35–39`). | Reuses existing snapshots, tree checks and sealed-descendant checks; fault wrappers serve concrete failures. |
| `probe_retained_failures.py` +1 | Preserves real synthetic witnesses without private material. | Reuses regression helpers; no new framework. |

Independent probe: fixed baseline **2 passed / 12 failed**; successor **14 passed / 0 failed**. All successor cases closed owned directory FDs and restored cwd. Final-input failures, actual result symlink rejection, partial writes and close failures retained external bytes and valid locators. Successful exits 0/1/2 cleaned only after matched inputs and completed result publication. The 282-member seal, file set, tree and link targets matched.

Inherited limits: result writes do not promise crash durability or atomic completeness; interrupted writes can remain partial. Mid-deletion failure, process termination and storage loss are outside these probes. No browser, ATS, model or production recovery was exercised. No formatting issues already enforced by tools are reported.

[独立原报告](standards/report.md) · [完整 smell baseline](standards/baseline.md)

## Spec

结论：0 findings。未发现缺失或部分实现的需求、范围扩张，或已实现但行为错误的明确需求。

规格：“最终输入核验和 result.json 写入成功后才删除临时目录，失败时保留外部原件和有效定位信息”（[request.md:3](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-targetclosed-rerun-finalization-fix-2026-10-12/request.md:3>)）。[rerun.py:427](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-targetclosed-rerun-finalization-fix-2026-10-12/rerun.py:427>) 先核验输入；435 行等待 JSON 写入器返回；437–438 行仅在输入匹配时清理。332–335 行的写入器使用实际流上下文，因此写入、flush 或 close 抛出异常不会触发清理。

独立公开 `main` 探针的最终唯一场景为 **33**，新旧入口各执行一次，共 **66** 次。新入口 **33/33** 通过；基准 **11/33** 通过。基准的 22 个不通过分为：16 个场景实际删除失败时应保留的外部原件，使定位指向不存在的目录；6 个成功场景在完整 JSON 可读前清理。它们是本变更修复的继承行为，不是新增缺陷。

覆盖最终输入 OSError/KeyboardInterrupt、不匹配、真实 result 链接/文件/目录冲突、write/flush/close 的 OSError/KeyboardInterrupt、pytest 0/1/2、suite/archive 异常，以及 child-artifacts、pytest-cache、case 的真实目录替换。每个失败场景核对实际外部 facts、有效 ZIP trace、XML 和 cache 字节，定位的路径/owner_pid/synthetic，以及保护哨兵完整树。每个成功场景在调用真实 rmtree 前读取完整 JSON 并核对原件。

目录绑定与 FD/cwd 机制继承不变。新入口 636 代、基准 732 代目录 open/dup 均逐代关闭；所有 cwd 恢复，所有保护哨兵树和字节不变。pytest 1/2 在最终化成功后清理符合 [README.md:15](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-targetclosed-rerun-finalization-fix-2026-10-12/README.md:15>)。未将未要求的崩溃持久化纳入缺陷标准。

证据：[probe-final.json](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-targetclosed-rerun-finalization-review-2026-10-12/spec/probe-final.json>)、[probe-final.log](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-targetclosed-rerun-finalization-review-2026-10-12/spec/probe-final.log>)、[执行源码](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-targetclosed-rerun-finalization-review-2026-10-12/spec/independent-probe-final.py.executed.txt>)。首轮 31×2 的 JSON/日志及两轮全部失败原证据保留；最终计数不累加首轮。联合回归、真实封存保护与私有聚合审计使用父代理证据，不计入此探针。Python 3.13.14、uv --locked、-B；无浏览器、ATS 或模型调用；生产恢复未验证。

[独立原报告](spec/report.md) · [唯一场景汇总](spec/summary-final.json) · [全部执行结果](spec/probe-final.json) · [外部原件复核](spec/retained-external-audit.json)

## 保留与封存

[初次保留核对](preservation-initial.json)全部通过。末尾原严格核对在旧哈希断言处失败；[失败日志](preservation-strict-failed.log)和旧核对器保持原样。新增只读诊断保留该失败，不把它改记为通过。[末尾保留核对](preservation-final-latest.json)覆盖目标包、其包外回执和全部旧证据：14 个封存包、私有原字节/元数据、私有诊断包及 04、06 closed 状态不变。

9 个哈希变化均位于未封存工作区：application_worker.py、career_portal.py、career_portal_data.py、portal_static/worker.js、application-worker-workflow.md，以及 test_ashby_drafts.py、test_hosted_ats.py、test_generic_worker.py、test_career_portal_http.py。本审查未写入这些路径；差异保留原样，发起者未确定。路径及前后公共哈希见 [只读漂移诊断](live-drift-observation.json)与末尾保留核对。Standards、Spec 结论及 280 项回归仅适用于固定封存入口和记录的副本输入。

只新增本审查包与包外封存后回执，未编辑封存包、私有证据或工单状态。[只读原生核对差异](native-readonly-isolation.diff)只改变审计根并将当前输入绑定单独报告，仍断言归档计数、事实对应、CRC 和封存 result。`evidence-hashes.json` 封存本包成员，回执为 `../application-worker-targetclosed-rerun-finalization-review-postseal-check-2026-10-12.json`。回执重新核对保护拒绝、归档和 3 份保留见证。所有结论仅限合成操作和只读证据复核，生产恢复仍未验证。
