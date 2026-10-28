# 复验入口修复的独立审查

2026-10-12，Europe/Zurich。只读审查已发布修复及证据，见[固定范围](review-scope.json)和[文本 diff](review.diff)。本轮只新增此审查包。

**仍有一处 P2 目录边界遗漏。** 当前修复包已封存，但新入口没有保护这个封存根。指定其不存在的子目录作为输出时，入口仍会接受，并向旧包增加归档文件。实际旧包未被执行这条路径，现有字节、文件集和票状态保持不变。

## 可达边界

[rerun.py:20](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-targetclosed-rerun-fix-2026-10-12/rerun.py:20>)至第 24 行只列原诊断、原审查和稳定性三个保护根。它遗漏当前已封存的 `application-worker-targetclosed-rerun-fix-2026-10-12`。第 35 行的检查因此放行它的不存在后代，第 37 行创建目录。

触发条件是封存后继续使用入口，并指定 `--output <已封存修复包>/new-child`，其中 new-child 尚不存在。独占创建保证叶子目录是新的，但旧父包的文件集随后增加。当前 35 项回归没有覆盖这个封存后边界。

[合成探针首次执行源码](probe_sealed_parent.executed.py.txt)使用字节一致的入口副本、临时合成封存父包及假 suite。它确认[以下观测](sealed-parent-observations.json)。当前 .py 副本只调整格式，首次源码和结果保留：

| 观测 | 结果 |
| --- | --- |
| 真实已发布修复包具有封存 manifest | true，只读检查 |
| 真实修复包的新后代匹配保护根 | false，只读计算，没有创建目录 |
| 合成封存父包下的新目录被 main 接受 | true |
| 合成父包原文件字节不变 | true |
| 合成父包文件集不变 | false，新增 invocation、pytest.log、result、temporary-workspace 四个文件 |
| 本轮 Browser 执行、实际旧包写入 | 均为 0 |

这项发现只针对当前已经封存、且本次明确要求保留的修复包。它不要求自动认定任意同名 manifest。后续修复应将此明确封存根纳入输出边界，并新增“封存父包的新后代被拒绝、父包文件集保持”的回归。原修复包继续保留。

## Standards

独立报告：[首次核对](standards.md)、[新增证据后的补充判定](standards-followup.md)。首次 0 项结论原样保留；补充结论为 **1 项 documented standard breach，最高 P2；0 项 heuristic smell**。

缺口违反 [CONVENTIONS.md:19](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/CONVENTIONS.md:19>)的封存证据保留规则及本轮整包保护范围。新目录独占创建没有覆盖已封存祖先的文件集。当前旧文件实际未变化。

其余规范核对通过：复用 checkout launcher、原测试及探针，未增加依赖；明确在 `/tmp` 创建 worker 工作区；超时原始流及失败附件保留；原隐私守卫和时限不变；合成与生产边界分开。

## Spec

独立报告：[首次核对](spec.md)、[新增证据后的补充判定](spec-followup.md)。首次 0 项结论原样保留；补充结论为 **1 项 missing/partial，最高 P2；0 项 scope creep**。

指定新叶子目录符合“新输出目录”条件，但遗漏当前已封存父包的保留条件。首次修复前的三个保护包仍受保护。这项发现涉及文件集增加，现有文件不会因此被同名覆盖。建议增加当前封存修复根的拒绝路径及对应回归。

其余规格核对通过：默认前缀覆盖环境值；同前缀的独立新目录保留历史；已有归档、用例与重复执行均拒绝；TMPDIR 和 tempfile.tempdir 不改变明确的 `/tmp` 选址。原 TimeoutExpired 对象、20 秒预算、命令和原始流不重写。facts/trace 在清理前保存；部分归档失败保留外部唯一副本及定位，不生成通过结果。

## 证据复验及实际保留

- [字节一致副本](copied-regression-inputs.json)在新的同层审查目录运行，[离线复验](offline-replay.log)为 **35 passed**，[XML](offline-replay.xml)为 0 failed / error / skipped。复制隔离了旧回归中向源码父目录创建临时目录的动作。
- [本轮保留与附件核对](preservation-and-evidence-audit.json)：**1819 个旧公开文件哈希、四个旧包的文件集均无变化**。文件集核对包含符号链接。私有原证据及私有诊断包另做字节、元数据和哈希核对，保持原状。04、06 仍为 closed。
- 既有最终矩阵仍为 26 passed，既有原红测仍为 1 failed。各轮失败、源码快照、修正和审查记录保留，没有把重复轮次相加。矩阵 26 raw facts / 3 traces、红测 1 raw facts / 1 trace 与原用例附件及执行输入对应；四份 ZIP 的 CRC 通过。本轮没有新原生执行。
- [本轮信号来源核对](signal-source-audit.json)读取六份既有合成材料。最初 SIGTERM 来源是源码 os.kill 路径、requested_signal 和 owned PID；stderr 没有独立初始 SIGTERM 记录。清理 SIGKILL 来源是同 PID 的 cleanup / force-kill / native-exit 行及匹配封存哈希的 SDK。Browser exitCode=143 和 worker returncode=2 保持不同含义。

原生产的关闭发起方仍未知，生产恢复仍未验证。35 项合成回归及附件检查不能改变这个结论。没有修改实现、验收、失败记录或票状态，没有提交或推送。

Standards：1 项，最高 P2。Spec：1 项，最高 P2。
