# 再次多轮审计 — 2026-10-25

本轮由 **9 位 agent、3 轮审查**完成。针对本轮结束核对的 **renderer v3 源码快照**，确认 **6 项 P2，无新增确认 P3**。
其中两项来自后继渲染改动，一项是预存的文本路径问题，另外三项涉及本轮修复边界及有条件的运行准入。
不能把这六项全部归因于此前四项修复，也不能把旧回归通过解释为所有相邻路径正确。

本轮只审计，没有修改产品源码、原测试、旧票或私人资料，没有执行修复、安装或真实申请。

## 版本与审计轮次

沿用先前确认的 HEAD；没有新提交。工作区含既有未提交和未跟踪工作，因此主要比较本次修复前精确字节与当前实现。
直接修复差异为六个生产文件、五个测试文件，并核对导航。修复完成后又有 Cover Letter 固定开头、结尾及岗位名槽的后继改动。

1. 首轮七线并行：规范、需求、队列、文件材料、配置与 HTTP 安全、renderer 历史兼容、证据与安装状态。
2. 第二轮交换视角：独立判断条件是否为正常支持入口、真实 v1 生产者是否准确、字段限额是否真正进入首次处理、后续表单或回读是否已提前阻断。
3. 第三轮两位新审查者分别复跑运行时正负对照及材料／renderer 反例；最终又以 v3 字节重验材料四项，排除新函数参数错误造成的误报。

审计期间外部代码从 v2 继续改为 v3，七个源码／测试文件相对尝试全套时发生变化。
本轮没有恢复或覆盖这些外部改动。最后的 v3 检查点及相应定向复验无漂移；详细快照、差异和过程日志保留在私人证据目录。
这是修复与后继差异的风险取样，不是逐行穷尽全仓库认证。

## Standards

### S1 · P2（条件性）：同一目录大小写别名绕过物理回调占用

位置：[application_match_refresh.py 第 35 行](../../src/career_evidence_graph/application_match_refresh.py#L35)。
占用集合按 `str(flow.root)` 比较。在大小写不敏感卷上，`FlowRoot` 与 `flowroot` 实际同目录、同设备、同 inode，
连 `.flow.lock` 也相同，但解析后的路径字符串不同。

公开 A.refresh_match 仍被屏障阻塞，旧 Flow 关闭后，使用大小写别名的新 Flow 实际取得同一根的所有权，
却看不到原匹配占用，能够启动 B.analysis。原样路径替换的正对照会正确拒绝 B。

条件限于大小写不敏感文件系统、同解释器 Flow 替换以及旧 callback 尚未返回。没有伪造路径解析或直接改 registry。
违反 CONVENTIONS 严格单岗顺序与本轮同根替换的保护目标；不声称已在真实 App 或远程模型上复现。

### S2 · P2：准备入口的反向运行顺序仍可跨岗重叠

位置：[application_match_refresh.py 第 821 行](../../src/career_evidence_graph/application_match_refresh.py#L821)。
先通过公开 Flow.start 或真实 loopback HTTP 启动 B.analysis 并保持运行，再对已有材料的 A 发起 fresh refresh，
A 的 callback 能执行并保存正常匹配回执，HTTP 返回 200，此时 B 仍未释放。

反向控制已有保护：A.refresh 先运行时，B.start 会被拒绝。当前新刷新只查询匹配回调集合，没有覆盖已在运行的其他阶段。
违反 CONVENTIONS 的单岗顺序及同岗材料并发／跨岗顺序要求。

范围是无 Pipeline 的独立准备入口及直接 Flow 调用；不泛化到具有额外当前岗守卫的默认 Pipeline HTTP。
没有手造 mode 或正在运行的任务状态；使用合法保留材料夹具及公开入口。

Standards：2 项确认 P2；最高问题均为有明确触发条件的跨岗执行重叠。

## Spec

### M1 · P2：缓存文本复用忽略收紧后的字符上限

位置：[application_materials.py 第 694 行](../../src/career_evidence_graph/application_materials.py#L694)。
已有 ready 文本在当前字段字符限额检查前被复用；相同正文若走新生成路径，则会正确拒绝超限。
独立反例先生成 96 字符材料，当前同字段上限变为 95 或 20 后，稳定采样、snapshot 检查和 prepare 仍通过，resolve 仍返回完整旧文本。

真实隔离 Chromium 与生产 ApplicationRunner.process 进一步证明：在 maxlength=20 的空 textarea 中实际写入了 20 字符前缀，
然后后置回读发现与完整原文不同，抛出 readback_failed。旧材料仍为 ready，已发生的截断填写变为待核对。
因此问题是已知限额未在自动填写前执行，不是已静默完成或能继续 Submit。

这是精确本轮修复前基线也存在的文本相邻缺口，不把它称为 PDF 文件约束修复的回退。
依据为既有字符限制与不裁切内容的交付要求。页面、授权及资料均为合成或替身，没有访问 ATS。

### M2 · P2（条件性）：零调用的预检失败进入无法自动核验的状态

位置：[application_materials.py 第 794 行](../../src/career_evidence_graph/application_materials.py#L794)及[第 824 行](../../src/career_evidence_graph/application_materials.py#L824)。
例如观测中的 max_bytes 为 Boolean 时，正确的严格检查在编译前拒绝它，编译次数为零；
但异常被保存成 needs_recheck，随后当前观测修正为合法上限，prepare 仍认为存在未决构建。

只读重查没有 export-intent 可读取，文件 retry 又只接已知 failed 尝试，所以 prepare、只读重查、文件重试三条自动路径均无法继续。
这不要求接受错误类型，也不要求恢复旧版把 Boolean 当整数处理的语义；拒绝本身正确，问题是纠正条件后的恢复分类。

依据 APP 的用户修正后一次继续、已知构建前失败可局部重试要求。条件限定为坏元数据随后变合法观测；
没有证明真实 ATS 必然提供 Boolean，也没有声称手工提供材料或 Skip 同样无解。

### R1 · P2：旧未决编译仅因 renderer 版本变化被阻止读取

位置：[application_cover_letter.py 第 924 行](../../src/career_evidence_graph/application_cover_letter.py#L924)。
用真实旧 v1 实现生成的原编译记录，在内容、未改 legacy 模板、TeX 及来源完全相同的情况下，
当前 v3 的 intent 全等比较因 renderer_revision 不同，在 read_compiled 前拒绝。

独立控制：同一原目录用 v1 只读 reconciliation 能读取准确完成结果，编译次数不增加；
当前公开 Worker 重查读取次数为零。它不是新 role 参数导致的 KeyError。

违反 APP-15 中 App／提示词变化不自动废弃已有 TeX/PDF、保留既有进度的要求。
仅旧未决编译的重查路径被证明；旧 ready v1 PDF 仍可复用，不能泛称全部旧 PDF 无效。
该缺口来自审计期间继续发生的 renderer 后继改动，不属于此前四项修复原反例。

### R2 · P2：旧稿只改正文，被固定结尾空行规范变化误拒

位置：[application_material_edit.py 第 9 行](../../src/career_evidence_graph/application_material_edit.py#L9)，关联[固定文本解析](../../src/career_evidence_graph/application_cover_letter.py#L236)。
未改变原 legacy 模板，只在旧材料完整文本里修改 BODY；当前代码重算固定 suffix 时保留了旧版扁平化时去掉的空行，
从而把合法正文编辑误判为 letter_fixed_text_changed。相同 payload 用真实旧 v1 映射可保存。

编辑 UI 以原 material.text 初始化，故这不是仅手构造的新版格式 payload。
它独立于 PDF intent 的 renderer 标签比较，与 R1 分开计数；违反历史人工稿保留及有效正文编辑的要求。
新增固定自我介绍和岗位名槽已有 PRD 支持，本轮不将它们当成范围扩大，也不因本项声称新模板整体不可用。

Spec：4 项确认 P2，分别为文本限额、预检恢复及两个旧记录兼容路径。四项不与多个复现日志重复计数。

## 已闭合的原修复与未新增的问题

- 原 M1 的文件 accept／max_bytes 在新建、缓存文件复用及上传选择中已统一；原 M2 的原始大小上限已持久化并在读取时消费。
- 原 Q1 的普通同路径 Skip／同根替换与直接新刷新守卫已有实现；本轮另测出以上两个受条件限制的剩余顺序问题。
- 合作 CLI 的跨进程锁覆盖最新 read／merge／atomic replace，只合并显式字段，在 serve 前释放；原 C1 直接反例已闭合。
- 原 S1 当前导航已纠正，没有新增确认 P3。旧七票继续关闭，没有重开或改写。
- legacy 从未保存过原大小限额时沿用已披露默认值，以及早已披露的缓存 PDF 丢失异常边界，没有被重复报成新增问题。
- 同岗操作、读取及已保存结果核验的原范围保持；没有新增批准状态或要求真实 Submit。

## 验证、漂移与安装边界

原完成版本的 **6,927 passed／2 skipped、6,929 节点**和 **39 项浏览器通过**已独立核对，记录准确。
但当前已有后继源码变化，不能把这些旧记录改称当前 v3 的全套通过。

本轮尝试重新跑完整默认回归；期间外部继续修改七个源码／测试文件，故中止并将其标为失效。
同期间的 48 项浏览器通过也不作为统一当前版本验收。没有隐藏或改写这些过程日志。
**本轮未形成当前 v3 的有效完整默认回归结论。**

采用的当前证据是：最新 v3 下两个材料反例独立复跑通过；真实 v1 生产者兼容反例及旧 ready PDF 正对照 4 项通过；
真实隔离 Chromium 的 helper／完整 process 对照 2 项通过；零编译预检恢复反例 1 项通过。
这些 passed 表示证明问题或正负控制成立，不表示产品通过。普通 renderer 定向 56 项通过，配置 CLI 29 项通过，HTTP 安全定向 29 项通过。
集合有重叠，不能累加成唯一用例数；早期 PDF 204 项及队列 69 项定向属于各自所记录的受查版本。

最新 v3 检查点的 650 项输入与结束核对一致，相关专项复验前后哈希无漂移。最新 Ruff、格式、diff 和 JS 语法检查通过。
初始到结束的外部后继变化另行记录；不能将“最终检查点无漂移”误写为整个审计期间无变化。

**2026-10-25 20:31:14 CET（Europe/Zurich）**只读核对安装包：126 项引擎内部一致，当前与工作区 **8 项差异**，12 项原生公开输入一致。
原修复结束时六项差异属于那个时点；新增 renderer／材料编辑后继使数量变化，不是旧记录造假。
本轮未执行 App、签名、权限或私人数据保全验收，没有安装或真实申请。

详细快照、源码差异、反例、控制和运行原始日志保留在私人证据目录；公开机器摘要仅保存布尔结论，见[verification.json](verification.json)。

Standards：2 项，最高 P2；Spec：4 项，最高 P2。共 6 项 P2，无新增确认 P3；不跨轴重排。
