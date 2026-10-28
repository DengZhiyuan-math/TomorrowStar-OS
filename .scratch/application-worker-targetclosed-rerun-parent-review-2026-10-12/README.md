# 封存父包保护修复的独立审查

2026-10-12，Europe/Zurich。本轮只新增此审查包。固定范围见 [review-scope.json](review-scope.json)与 [review.diff](review.diff)。原修复包、诊断包、验收、失败记录及 04、06 状态保持原状。

**仍有两处 P2 保护边界遗漏。** 已有 71 项通过和封存后拒绝记录在所测路径上有效，但没有覆盖文件系统大小写别名及父链接改指后的目标变化。以下反例不改写真正旧包，不改变原通过／失败记录。

## 可操作发现

### P2：APFS 大小写别名

[原入口第 38 行](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-targetclosed-rerun-parent-fix-2026-10-12/rerun.py:38>)按 Path 组件拼写比较根。本机 APFS 的大写目录别名 exists / samefile 均为 true，resolve 仍保留大写拼写。指定 `<大写保护包名>/新子目录`，guard 不匹配，执行到 mkdir。

[首次执行源码](probe_case_alias.py.executed.txt)、[首次观测](case-alias-observations.json)、[修正探针绑定后的复验](replayed-probes/case-alias-observations.json)确认六个旧／自身根的两种前缀共 12 条路径均到达 mkdir。只读 spy 在创建前抛出异常；真实文件没有创建。此触发不需要并发变化。

修复应按现存祖先的文件系统身份判断是否属于保护包，避免只依赖区分大小写的字符串比较。新增本机大小写别名回归，并保留对大小写敏感卷的正确行为。

### P2：校验后重新解析父链接

原入口第 38 行在保护比较中解析原路径，[第 40 行](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-targetclosed-rerun-parent-fix-2026-10-12/rerun.py:40>)再次解析，第 41 行创建最后一次结果。父符号链接在相关比较之后改指时，会核验一个目标，却创建另一个未通过检查的目标。

[首次一根见证](path-boundary-observations.json)使用原 Path.resolve 与真实 symlink 改指，main 在合成保护根下新增七个路径、调用假 suite 并返回 0。[六根见证](six-root-retarget-observations.json)及[复验](replayed-probes/six-root-retarget-observations.json)保留原六根顺序，覆盖旧诊断根／自身根与两种前缀，共四项均复现。旧诊断根在第一次检查后改指；自身根在第六次检查后改指。第七次解析选入保护根。

探针 hook 仅安排真实链接改指的交错时点，解析仍调用原 Path.resolve。suite 是假实现，Browser 为零，所有写入只发生在 `/tmp` 合成父包。这是具体 check/create 交错见证，不是历史生产故障复现。

修复应固定通过检查的解析目标，并对同一目标执行创建，避免创建前再次解析原父链接。补旧根与自身根的链接改指回归；继续核对稳定路径、叶子链接及 `..` 行为。

## Standards

[首次稳定路径报告](standards-initial.md)为 0 项；[首次补充](standards-retarget-followup.md)为 1 项 P2；[最终报告](standards-final.md)为 **2 项 P2 documented breaches，0 heuristic findings**。两个缺口均违反封存证据保留规则，原报告不重写。

## Spec

[最终独立报告](spec-final.md)为 **2 项 P2 implemented-but-incorrect，0 scope creep**。同两处缺口导致后代拒绝与父包保留要求不完整，没有重复计数。

## 复验与实际保留

- [字节一致副本](copied-regression-inputs.json)在新的同层目录执行，[回归日志](offline-replay.log)与 [XML](offline-replay.xml)为 **71 passed，0 failed / error / skipped**。没有从封存源码目录运行会创建 TMPDIR 临时目录的测试。
- 原 source 的 [24 条稳定路径见证](path-boundary-observations.json)均在 mkdir 前拒绝。包外 `..` 不再创建封存中间目录，既有直接／alias 逃逸回归仍通过。
- [独立封存后实际 CLI 检查](independent-postseal-rejection.json)对六个根、空／重复前缀共 12 条正常拼写路径返回 2，没有创建输出。原单独的封存后收据也按封存 manifest 哈希匹配。以上收据不覆盖两处新反例。
- [本轮保留与附件核对](preservation-and-native-evidence-audit.json)：**2552 个受保护公开文件哈希、六个旧包文件集均不变**，含前轮 1840 个旧哈希、最新修复包全部文件及原封存后收据。原 683 项 manifest 与自身哈希匹配。私有原证据不变，04、06 仍为 closed。
- [原验收的实时只读核对](saved-evidence-live-audit.json)与封存结果匹配。原矩阵仍为 26 passed，原红测仍为 1 failed；27 raw facts / 四份 native traces 保留，ZIP CRC、原始 facts 与用例对应、最终源码绑定及两份外部全量归档复制核对均通过。本轮新原生 Browser 执行为零。
- 默认与重复前缀、重复执行、TMPDIR／tempfile.tempdir、原 20 秒 TimeoutExpired 与原始流、facts/trace、部分归档失败及外部完整副本／定位文件保留仍由 71 项副本回归覆盖。原时限与原断言的封存哈希保持不变。

新增探针首次源码保存为 `.executed.txt`。初次 [Ruff](ruff-check.log)报告两个同步闭包的 B023，修正为显式绑定后在新 [replayed-probes](replayed-probes) 目录复验，不覆盖初次观测。[最终 check](ruff-check-final.log)和 [format](ruff-format-final.log)通过。该修正只影响本轮诊断脚本，原实现和回归副本不变。

SIGTERM 请求仍由 probe 的请求字段、owned PID 和 os.kill 路径支持；后续清理 SIGKILL 由同 PID stderr 顺序及固定 SDK 源码支持。native exit 143 与 worker returncode=2 分开记录。生产发起方未知，生产恢复仍未验证。两处输出保护问题不改变 04、06 的状态或原验收记录。

Standards：2 项，最高 P2。Spec：2 项，最高 P2。
