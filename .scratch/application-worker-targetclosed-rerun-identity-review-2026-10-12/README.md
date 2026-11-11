# Identity 修复包独立审查

2026-10-12，Europe/Zurich。本轮只新增此审查包。固定输入见 [review-scope.json](review-scope.json)和 [review.diff](review.diff)。被审查入口的 SHA-256 为 `9d1db77d947233456754b3a8847760b8ff6d23fe5b7d6eb082bb01ee7b107d91`；封存 manifest 为 `3e66f13f8ce020ec1108b040383864a85a35d77e3f2b6f0d1af0361afe426f2a`。

**仍有一处 P2：解析后的父目录身份可在创建前变化。** 大小写别名和原输入链接改指的修复在复验范围内有效。单次解析固定路径名称，但没有固定创建所经过的目录身份。

## Standards

[独立报告](standards/report.md)：**1 项 documented P2，0 heuristic findings**。两个合成见证及复验确认：第 [50–51 行](../application-worker-targetclosed-rerun-identity-fix-2026-10-12/rerun.py)创建前，将已检查的真实父目录替换为指向合成保护根的真实链接，`reserve_output` 仍正常返回并新增目录。这违反 `CONVENTIONS.md:19–20` 的封存证据保留规则。

初次 [观测](standards/resolved-ancestor-observations.json)、[执行源码](standards/probe_resolved_ancestor.py.executed.txt)、[复验](standards/resolved-ancestor-observations-replay.json)及[源码核对](standards/source-verification.json)保留。八个本机大小写别名在 mkdir 前拒绝。

## Spec

[独立报告](spec/report.md)：**1 项 implemented-but-incorrect P2，0 scope creep**。同一缺陷使“拒绝其后代输出”不完整，不另计 missing finding。新增父链接与替换既存父目录两种交错均复现；八根集合的旧根／自身根、空／重复前缀共八项见证，`main` 返回 0，假 suite 调用一次，并在合成保护根创建归档。

初次 [观测](spec/resolved-parent-race-observations.json)、[执行源码](spec/probe_resolved_parent_race.py.executed.txt)与[复验](spec/resolved-parent-race-observations-replay.json)保留。首次与复验的外部合成目录也保留。探针绑定与格式修正仅修改新审查脚本，原实现未修改。

两轴指向同一缺陷，没有重复计为两处缺陷。后续创建需绑定到已核验的目录身份，并覆盖缺失父目录与既存父目录两种交错。

## 独立边界复验

[父代理探针](probe_boundaries.py)直接载入原封存入口，保留真实 `resolve` 和 `mkdir`。hook 只安排真实链接操作的交错时点。suite 是假实现；所有写入位于 `/tmp` 合成根，Browser 执行为零。[观测](boundary-observations.json)区分以下结果：

| 交错 | 见证数 | 结果 |
| --- | --- | --- |
| 检查后仅改指原输入 alias | 4 | 原输出只解析一次，创建仍在已检查的安全目录；合成保护根不变 |
| 检查后向不存在的已解析父路径插入链接 | 4 | mkdir 进入保护根；新增七个归档路径；main 返回 0 |
| 检查后移走既存已解析父目录并用链接替换 | 4 | 同样进入保护根；main 返回 0 |

缺失父目录的最小交错如下。两步之间的文件系统变化不会改变路径字符串。

```text
guard 检查 /safe/missing/fresh（missing 尚不存在）
  -> 创建 /safe/missing -> /sealed 的真实链接
  -> mkdir(/safe/missing/fresh) 创建 /sealed/fresh
```

本轮没有从封存源码目录运行测试。四份回归输入的[字节核对](copied-regression-inputs.json)通过，在本审查同层副本执行的[日志](offline-replay.log)和 [XML](offline-replay.xml)为 **124 passed，0 failed / error / skipped**。这些复制文件只用于回归，没有发布新的运行入口。

[实际原入口 CLI 检查](independent-cli-rejection.json)为 **32 次拒绝，exit 2**，覆盖八个保护根、正常／大写拼写和两种前缀。每次先通过 mkdir spy 确认安全，再执行实际 CLI。新输出未创建。大小写敏感卷的原生验收仍未执行；既有模拟身份回归通过。

原 20 秒超时、原诊断断言、超时原始流、部分归档失败、TMPDIR 和叶子链接行为继续由字节一致回归覆盖。通过的稳定路径检查不覆盖上述两个新交错。

八份新审查 Python 文件的最终 [Ruff check](ruff-final-check.log)和 [format](ruff-final-format.log)通过。初次探针的 lint 失败与执行源码保留，修正后的探针在新结果文件中复验，没有覆盖首次观测。

## 保留与范围

[最终只读核对](preservation-final-audit.json)确认 **2646 个受保护公开文件哈希、八个旧包文件集、目录树及链接目标不变**，包含 identity-fix 自身及其封存后收据。原封存 manifest 有效。私有原证据字节／元数据、私有诊断包不变；04、06 保持 closed。

[原证据实时核对](source-evidence-live-audit.json)通过。原矩阵、原红测、raw facts 和 native traces 保留。SIGTERM 请求、后续清理 SIGKILL 与 native exit 143 仍保留不同来源和含义。本轮没有新的 Browser、ATS 或模型执行；生产发起方未知，生产恢复仍未验证。

本包的 [evidence-hashes.json](evidence-hashes.json)保存新增审查材料。后续复跑回归需先复制到全新同层目录，避免原 TMPDIR 回归向封存目录创建临时目录。[verify_review.py](verify_review.py)使用 `python -B` 只向 stdout 打印只读核对结果；输出应保存到包外。

Standards：1 项 P2。Spec：1 项 P2。两轴指同一缺陷。
