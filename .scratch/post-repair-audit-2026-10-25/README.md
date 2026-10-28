# 修复后多轮并行审计 — 2026-10-25

本轮只审计。八位 agent、六个首轮角度、三轮审查，确认 **4 项 P2、1 项 P3**。
没有执行修复、修改产品源码／测试、改动旧票、创建修复计划或执行安装。
这些是当前版本仍可触发的问题，不表示此前五项修复均未生效。

## 范围与轮次

沿用用户确认的 HEAD `e4a26d0c24311d014d478f7f92e58a88e6709b4b`。
没有新提交；`git diff HEAD...HEAD` 与 `git log HEAD..HEAD` 为空。工作区含既有未提交、未跟踪内容。
本轮以修复开始前的精确字节对比当前 **6 个生产 Python、6 个测试文件**，并审查相关调用及当前导航；
`git diff HEAD --` 仅作更广工作区参考，不把 HEAD 外的大量既有工作错误归因于这轮修复。

1. 首轮并行：Standards、Spec、跨岗运行与恢复、PDF／材料、配置／HTTP安全、交付与安装证据。
2. 第二轮独立反证：材料候选交由 Spec 另写公开入口反例；导航状态由 Standards 复核；排除旧表单状态、未消费页面限额的替身、未经规范化的模式等可能造成的误报。
3. 第三轮：另一集成审查者复跑跨岗与材料反例；另一配置审查者使用独立 CLI 进程和真实临时端口验证并发条件。没有直接采信作者的结论。

风险取样覆盖修复差异与相邻 Interface，不是全代码库逐行认证。

## Standards

### S1 · P3：当前导航仍称七票未领取

位置：[修复目录 README 第 6 行](../audit-repair-plan-2026-10-25/README.md#L6)。
该入口仍直接称“本轮仅规划，七张新票全部 open、未领取”，未限定为历史。
实际地图、实施交接和七票均已关闭，随后还完成了安装同步。违反 CONVENTIONS 的阶段状态区分及当前决策导航规则。
影响仅为进度认知；不能据此反证功能修复或安装接受。

`planning-verification.json` 明确是历史规划快照，不重复计为问题；有明确历史限定的地图及旧安装记录同样不计。

[独立规范复核](verification/standards-round2.md)。

Standards：1 项确认发现，最高 P3（当前导航状态不一致）。

## Spec

### M1 · P2：已有 ready PDF 复用绕过当前格式要求

位置：[application_materials.py 第 666 行](../../src/career_evidence_graph/application_materials.py#L666)。
已有 ready 材料在新格式检查之前直接复用。先在 `.pdf` 字段生成 PDF，再把当前同字段的 `accept` 改为 `image/*`，
公开 prepare 仍返回 ready，随后上传方法的替身控件收到 `application/pdf`。

独立反例使用真实表单 capture 完成旧、新观察的稳定采样：当前 snapshot 确为 `image/*`，无 intervention_pending，
真实 check_snapshot 通过。它不是旧页面状态尚未刷新导致的假象，也不是将原新生成子串误判重复计数。
R04 的当前字段格式限制只在新生成路径闭合，复用路径仍残留。

依据：R04 验收要求拒绝 `image/*`／`text/*`，Cover Letter PRD 要求明确处理非 PDF 限制。
本轮证明到达合成上传调用；没有证明某个真实网站接受了该 PDF。

### M2 · P2：PDF 重查丢失原页面大小限制

位置：[application_worker.py 第 3091 行](../../src/career_evidence_graph/application_worker.py#L3091)。
重查的本地与远端读取都没有继续传入原字段的 `max_bytes`，使用 helper 默认上限。

生产默认材料分派实测：字段限额 70,000 字节、PDF 77,015 字节，正常收到编译结果时返回 `letter_file_too_large`；
同一编译如果完成后响应丢失，经公开重查却采用为 ready。再次 prepare 后，合成上传控件仍收到 77,015 字节。
另一独立反例确认首次分派确实消费 64,000 字节限额，重查却接受同一 77,015 字节结果，排除了替身忽略限额的解释。

依据：Cover Letter 第 05 决策已规定处理页面文件大小限制。恢复不应使同一结果从超限变为可交付。
没有重编译或调用真实 Prism；网站最终如何校验未知。

两项材料发现由不同角度审查者独立复现，分别计数；多个探针不重复计数。
[Spec 最终报告](verification/spec-final.md)、[PDF 专项](verification/pdf-audit-round1.md)、[第三轮快照复核](verification/round3-independent-accept-followup.md)。

Spec：2 项确认发现，最高 P2（当前格式与原大小约束在不同路径失效）。

## 专项：运行时与配置完整性

### Q1 · P2：Skip 后旧匹配未返回，新岗已开始分析

位置：[application_pipeline.py 第 1522 行](../../src/career_evidence_graph/application_pipeline.py#L1522)，关联 `_leave_current` 和锁外匹配 callback。

合法当前岗 A 的 HTTP refresh-match 已开始，匹配 callback 被同步屏障阻塞。
公开 Skip 后，B 经公开创建、admit 及正常 tick 创建任务并进入 analysis；此时 A 的匹配仍在运行。
最终采用检查确实以 409 拒绝 A，但无法撤销已经发生的跨岗调用重叠。

这与原 R02 的“初始请求来自非当前岗位”不同：初始准入合法，缺口发生在后续切换。
违反 CONVENTIONS 严格单岗执行要求。A 的旧材料与初始 paused/current 状态来自合成夹具；B 没有手造 Flow 任务。
HTTP 为真实 loopback，匹配与分析是显式替身；邮件轮询关闭，没有调用真实模型或 ATS。

[首轮专项](verification/queue-review-round1.md)、[第三轮独立复核](verification/round3-independent-integration.md)。

### C1 · P2（有条件）：并发配置保存丢失一方更新

位置：[career_portal.py 第 3586 行](../../src/career_evidence_graph/career_portal.py#L3586)。

两个合法 CLI 写者读取同一旧配置，一方仅选新模板，另一方仅选新 manifest，随后均成功保存。
原子替换保证 JSON 文件完整，但后写者仍用旧快照覆盖前一方的新值。

第三轮用两个独立进程、同一临时 HOME 的默认配置、真实且不同的 loopback 端口复现，两次 exit 0。
同步屏障仅固定正常 read／merge／replace 的交错。触发前提为不同端口或 `--port 0` 的并发保存；
默认端口冲突通常会让第二实例失败，不能泛称所有双启动或单次保存都会丢字段。
单一安装 App 身份不等于 CLI 配置写者互斥。R01 原单写者保留字段的直接修复仍有效。

[配置专项](verification/config-security-round1.md)、[第三轮独立进程复核](verification/round3-config.md)。

## 原修复点的复核范围

| 工作包 | 本轮结论 |
| --- | --- |
| R01 | 单次保存的字段合并、坏配置拒绝和原子失败保护通过；另发现并发丢更新。 |
| R02 | 初始非当前岗请求准入已修；另发现运行中匹配跨 Skip 的占用缺口。 |
| R03 | 两个恢复入口的跨岗 pending 检查及合法零新作者恢复通过所查回归。 |
| R04 | 新生成完整 token 比较已修；ready 材料复用仍绕过当前格式限制。 |
| R05 | 原编译结果已可只读取回，旧符号链接及完整损坏本地证据保护通过；原字段大小未沿用。 |
| R06 | 指定的开发计划状态已纠正；同目录 README 仍有一处未标历史的旧状态。 |

旧票保持原状态，不把本轮发现擅自改成新的修复任务。
JD 明确 PDF 与页面文本入口优先级仍有解释空间，不作为确定缺陷。
纯 export.json mtime 变化及已说明的依赖策略兼容没有被计为额外问题。

## 验证与证据边界

- 历史完整默认结果 **6,882 passed／2 skipped，6,884 节点、386 文件** 经独立复核：无遗漏、重复或额外结果，四组退出码为 0。
  其 611 项冻结输入与当前字节一致。本轮未重复该全套，不将旧记录改称新运行。
- 本轮独立定向集：Standards 41 passed，跨岗 39 passed，配置／HTTP／安全 163 passed，PDF 147 passed／1 deselected，Spec 149 passed／1 deselected。
  这些集合有重叠，不能相加为唯一测试数。
- 新反例日志中的 passed 表示“违例成功复现”，不表示产品通过。已有回归全绿不消除本报告发现。
- 本轮 Ruff、格式、diff 和相关 JS 语法检查通过。
- 产品源码、测试、脚本与 macOS 输入从本轮开始到结束无漂移。审计期间两个导航文档由外部安装后继更新，分别记录，不伪称全部输入零变化。
- 本轮只新增审计报告和合成证据，没有改产品代码、原测试、旧票或真实配置，没有执行修复或安装。

[机器摘要](verification.json)。具体反例脚本保存在 `verification/probes/`；完整初始差异和私有工作日志另存本轮审计目录。

## 安装状态按时点区分

首轮只读比较仍为七项源码差异。审计期间，其他执行完成了后续主 App 同步，当前导航及安装交接已有明确后继记录。
**2026-10-25 19:39:42 CET（Europe/Zurich）**重新只读核对：126 项包内引擎与清单一致，和当前源码 **零差异**；12 项原生公开输入一致。

本结论仅为文件字节核对；本轮没有重新验证已加载进程、代码签名、实际权限、私人资料保全或原生运行。
新安装记录中的这些运行结论属于其各自验收，不由本次 SHA-256 比较推出。
旧七项差异报告带有明确时点，不计为错误，也不能继续当作当前状态。

[第三轮当前安装证据](verification/evidence-round3-current.md)。本轮未执行真实模型、用户 Prism、ATS 或最终 Submit。

Standards：1 项，最高 P3；Spec：2 项，最高 P2；专项：2 项 P2。合计 4 项 P2、1 项 P3，不跨轴重排。
