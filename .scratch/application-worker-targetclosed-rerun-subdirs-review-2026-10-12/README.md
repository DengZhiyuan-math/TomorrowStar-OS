# subdirs-fix 独立审查 — 2026-10-12

Standards：0 项规范违规，0 项启发式问题。Spec：0 项发现。未发现本次修复引入的缺失要求、越界行为或错误实现。两轴由独立代理分别检查；探针直接加载封存源，未根据另一轴结果调整判断。

固定基准为 dirfd-fix 的 `rerun.py`，SHA256 `d4a167e63503c9a982952bf09fa949cb242f8c1a46c8a9ecacbf3502e8151ebe`。目标为 subdirs-fix 的 `rerun.py`，SHA256 `12c11c5eb9b1331bd46bb276b748f402fcc17174c59b21431f78b747ac4f3e76`。源包清单 SHA256 `1f01d9dbb851e1571b6f051c509658b910914266f7d48e926dd19557b4aa83a4`，267 个成员有效。Git HEAD 仅作元数据，commits 为空；比较的是封存包，不是 Git 分支。

[范围](review-scope.json)、[差异](review.diff)及[请求](request.md)固定输入。原规格为源包 request.md 与 README.md。规范为仓库 AGENTS、README、CONVENTIONS、ARCHITECTURE、PROJECT 和数据边界。`docs/agents/issue-tracker.md` 未配置；本次使用用户明确提供的本地请求和封存包谱系。

| 检查 | 最终结果 |
| --- | --- |
| Standards 独立探针 | 22 passed；首次与最终为 18 + 4，不相加轮次 |
| Spec 独立去重探针 | 299/299 passed；12 个合成保护根树、字节及链接不变 |
| Spec 目录 FD 账本 | 6036 次获取均关闭；缓存描述符及关闭后的编号复用均检查 |
| 既有回归副本 | 255 passed；0 failure/error/skipped |
| 实际封存源 CLI | 48/48 拒绝；12 根 × 正常/大写 × 空/重复前缀 |
| 最终化新旧对照 | 4/4 通过；是附带行为观察，不计新缺陷 |
| 旧公共证据 | 3282 个哈希、12 个包文件集、完整树及链接目标不变 |
| 私有证据 | 原始字节/元数据及私有诊断包不变，仅输出聚合结果 |
| 工单 | 04 closed；06 closed |
| 新浏览器/ATS/模型调用 | 0 |
| 生产恢复 | 未验证 |

目录探针覆盖 cases、case、matrix 及后代，child-artifacts 与多层附件父目录，以及 pytest XML/缓存导入。打开前的链接替换被拒绝；打开后及连续写入间的替换仍在已持有目录写入。目录创建/打开、文件打开/copy、probe 链接、cwd 进入、suite 异常和 FD 复用均检查关闭和工作目录恢复。

副本位于本新审查目录。为保留被审源包，复制入口只增加源包的保护根；集合断言同步增加一项。目录绑定和写入实现不变。其余副本字节一致。精确差异和哈希见 [副本审计](regression-copy/audit.json)、[隔离差异](regression-copy/isolation.diff)。[日志](regression-copy/offline.log)、[XML](regression-copy/offline.xml)和执行源码快照均保留。封存后不要在审查目录重跑离线测试，旧 TMPDIR 反例会在源码副本目录临时创建目录。

封存原生证据复核通过：原矩阵 26 pass、历史红测 1 项预期失败，27 raw facts 与 4 native traces 的对应、CRC、输入绑定及外部完整归档复制均有效。这是已有证据的只读核对；本次未新增浏览器运行。[源包封存复读](source-postseal-replay.json)保留结果。

附带观察：最终输入核验或 result.json 写入失败之前，temporary staging 已删除。此顺序在两版均存在；完整 facts、trace、XML 与缓存归档仍在，定位文件指向已删除的 staging。未观察到原始证据丢失。此观察不作为本次子目录修复的新发现；具体触发和字节核对见 Spec 对照证据。

## Standards

硬性规范违规：0。启发式 judgement calls：0。未确认本 diff 引入的违规；未把继承限制列作新问题。

审查基准为封存 dirfd-fix，目标为封存 subdirs-fix；`commits=[]`，Git HEAD 仅作元数据。已核对两份 `rerun.py` 的指定 SHA256，并检查七文件 diff、AGENTS、README、CONVENTIONS、ARCHITECTURE、数据边界、PROJECT 与包内 request/README。

独立合成 probe：22 passed。直接以 `-B` 加载目标封存源，使用 locked Python 3.13 与 checkout launcher；全部测试工作目录在 `/tmp`。

首次/最终结果：`test_independent_probe.py` 均为 18 passed；`test_metadata_probe.py` 均为 4 passed。每个 probe 只执行一次，未修订重跑；失败 0，跳过 0。原始日志与 XML 保留。

- 六层目录的打开前链接替换均拒绝；打开后替换的连续写入均保留在原目录。
- 四种异常路径核对所有捕获的 open/dup FD 关闭、cwd 恢复和外部原件保留。
- 已关闭 case 的 FD 被复用后仍拒绝写入；文件链接替换不会截断 sentinel。
- 完整入口的 pytest XML 与两层缓存导入保留相同目录绑定。

`rerun.py:106-224` 的受限适配器服务于原写入器实际使用的操作。标准库 `dir_fd`、`O_NOFOLLOW`、`ExitStack` 满足当前需求；未发现必须新增抽象或依赖的缺口。已逐项检查完整十二项 smell baseline，详见 `heuristic-baseline.md`。规范优先；smell 不作硬性违规；工具强制的格式规则跳过。

证据为 `probe-run1.log/xml`、`probe-run2.log/xml` 和两个独立 probe 源文件。无真实浏览器、ATS、模型或生产恢复执行。未修改封存包、私有证据或工单状态。

[独立原报告](standards/report.md) · [完整启发式基线](standards/heuristic-baseline.md) · [探针记录](standards/probe-results.md)

## Spec

可执行发现：0。未发现缺失要求、越界行为或错误实现。

判断依据为 `request.md:3,5` 的“将子目录创建和后续归档写入也绑定到已核验的目录身份”及封存、私有证据、工单和合成验收边界；另核对 `README.md:5–9` 的具体目录与清理承诺。审查比较两个封存入口，不把 HEAD 当作实现基准。

最终去重探针为 **299/299 通过**；另有 **4/4 基准对照**。早期轮次不累加。用锁定 Python 3.13.14、`-B` 和 `/tmp` 合成工作目录运行，真实浏览器、ATS 与模型调用均为零。封存源字节未变。

探针覆盖 cases、case、matrix 两层后代、child-artifacts 五层链和缓存四层链；验证创建/打开前后替换、连续写入间替换、五个父目录同时替换、文件链接、部分 copy 后异常、probe 链接失败、cwd 进入失败、套件退出及关闭后的 FD 编号复用。12 个合成保护根的完整目录树、链接与文件字节均未变。成功路径在持有目录产生预期字节。失败路径恢复 cwd，保留此前产生的原始 facts/trace。6,036 次目录 FD 获取均有对应关闭；复用后的五项操作均被拒绝。

候选不列入 finding：`rerun.py:425–435` 先删除 temporary，再核验输入与写 result.json，弱于 `README.md:9` 的“若套件或归档抛出异常，保留外部原始文件”。真实 result.json 链接拒绝及最终哈希异常在新旧两版均复现；基准对应 `rerun.py:269–280`。两版归档仍有逐字节完整的 facts、trace、XML 和缓存，定位文件保留但指向已删除的 staging 目录。未观察到原始证据丢失，也未形成这次子目录修复的新缺陷。

正式证据：`deduplicated-results.json`、`deduplicated-summary.json`、`deduplicated.log` 和 `independent_probe.py`。旧轮次及未触发的早期基准注入原样保留。旧公共哈希、私有聚合和工单状态由父审查独立核对；本报告不将其预报为通过。生产恢复未验证。

[独立原报告](spec/report.md) · [正式去重结果](spec/deduplicated-results.json) · [汇总](spec/deduplicated-summary.json)

## 保留与封存

[最终保留核对](preservation-final.json)覆盖源包、其包外回执和全部旧包。只新增本审查包与包外封存后回执；未修改封存包、私有材料或工单状态。`evidence-hashes.json` 封存本包成员；包外回执为 `../application-worker-targetclosed-rerun-subdirs-review-postseal-check-2026-10-12.json`。所有结论仅限合成目录操作和只读证据复核。生产恢复仍未验证。
