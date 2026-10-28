# Dirfd 修复包独立审查

2026-10-12，Europe/Zurich。本轮只新增此审查包。固定输入见 [review-scope.json](review-scope.json)和 [review.diff](review.diff)。被审查 runner 的 SHA-256 为 `d4a167e63503c9a982952bf09fa949cb242f8c1a46c8a9ecacbf3502e8151ebe`；原 manifest 为 `36f0163e20e7f4a6615c77a607ba8a27699d7ed57e1adcc24f3e59b138a803f4`，252 项成员均核对。

**两个独立轴均未发现本次差异新引入的可操作问题。** 此结论针对已检查的输出祖先与归档根身份绑定。归档内部子目录的链接替换仍是旧基准和新版共同存在的边界；不能把本结论解释为任意归档子树的安全保证。

## Standards

[独立报告](standards/report.md)：**0 项本次差异引入的 documented violations，0 项 actionable heuristic smells**。

原生 `dir_fd`、`O_NOFOLLOW`、`fstat`、`fchdir` 与 `ExitStack` 满足标准库／原生能力优先和最小改动规则。兼容 `reserve_output` 包装有既有接口需求，没有以 Middle Man 启发式另列问题。

[八项独立探针](standards/observation.initial.json)及[执行源码](standards/probe.initial.py)确认已打开父目录替换、缺失父链接拒绝、cases 创建失败、suite 异常、原工作目录打开失败和归档入口 `fchdir` 失败的行为。工作目录恢复，跟踪的目录描述符关闭。原入口及基准哈希不变。

## Spec

[独立报告](spec/report.md)：**0 项本次差异引入的可操作 Spec 问题，0 scope creep**。在输出祖先／归档根绑定范围内，没有复现 missing／partial 或 implemented-but-incorrect 要求。

[最终 52 项复验](spec/directory-binding-observations-attachment-replay.json)覆盖 13 种交错／异常、旧根／自身根及两种前缀。缺失父链接在 mkdir 前插入时拒绝；打开后的父目录或输出名称被替换时，创建及后续写入仍在原目录身份上。新父目录和输出目录的 mkdir/open 边界也覆盖。cases 创建、原 cwd 打开、入口 fchdir、suite 与附件复制异常均检查目录描述符关闭和 cwd 恢复。附件异常保留外部原件。

初次 [观测](spec/directory-binding-observations.json)、[执行源码](spec/probe_directory_binding.py.executed.txt)、[首次复验](spec/directory-binding-observations-replay.json)、[附件扩展源码](spec/probe_directory_binding.attachment-expanded.py.txt)和各轮 lint 日志保留。修正仅作用于新探针，没有修改封存实现或覆盖首次结果。

## 共同保留的归档子目录边界

此项单独记录，不归入本次新引入问题。两个独立报告均记录 cases 边界，父代理另通过完整 `main` 核对 cases 和附件路径。

| 改变的位置 | 已固定身份 | 仍通过名称解析的部分 | 观测 |
| --- | --- | --- | --- |
| 输出祖先或输出名称 | 父目录描述符、输出目录描述符和 cwd | 原输入名称不再用于归档根写入 | 在复验交错中保持原目录 |
| `archive/cases` | archive 根 | `prepare_case` 的 cases 子路径 | 链接替换可将 case 创建及写入引向合成保护根 |
| `archive/child-artifacts` | archive 根 | `retain_attachments` 的附件子路径 | 链接替换可将附件复制引向合成保护根 |

[父代理执行源码](probe_descendants.py.executed.txt)、[首次观测](retained-descendant-observations.json)和[格式修正后复验](replayed-descendants/retained-descendant-observations.json)保留。两种位置、两种版本、旧根／自身根共 **8 个见证**。两版各组新增路径完全一致；main 均返回 0。原合成 facts 字节保持不变，但合成保护根的目录树增长。所有改变只发生在新归档和 `/tmp` 合成根，真实封存包没有写入。

Spec 的[独立基准／新版 cases 复验](spec/retained-cases-observations-replay.json)得到相同边界。输出根身份绑定没有固定每一个归档子目录的身份。

## 副本回归与真实拒绝

五份 [回归输入字节核对](copied-regression-inputs.json)通过。[新副本日志](offline-replay.log)和 [XML](offline-replay.xml)为 **166 passed，0 failed / error / skipped**。没有在封存源码目录运行会创建 TMPDIR 临时目录的测试。

[原入口实际 CLI 检查](independent-cli-rejection.json)为 **40 次拒绝，exit 2**，覆盖十个根、正常／大写拼写和空／重复前缀。每次先用两种 mkdir spy 确认安全，再执行 CLI。新输出没有创建。上述通过不会扩大归档子目录的保证范围。

原 20 秒时限和原诊断断言仍由原回归及封存哈希核对。大小写敏感卷原生验收仍未执行；既有模拟身份回归通过。

九份维护中的 Python 源码的最终 [Ruff check](ruff-final-check.log)和 [format](ruff-final-format.log)通过。初次执行快照保持原样；新脚本的首次 lint 失败保留。原 Standards 和 Spec 报告分别保存为各自的 `report.initial.md`，附件边界补充没有覆盖初版。

## 实际保留核对

[最终核对](preservation-final-audit.json)确认 **2946 个旧公开文件哈希、十个旧包文件集、目录树及链接目标不变**，包含 dirfd-fix 全部封存成员及包外收据。原 manifest 有效。私有原证据字节／元数据和私有诊断包不变；04、06 保持 closed。

[旧包只读核对](source-preservation-live-audit.json)和[保存的原生证据核对](saved-native-live-audit.json)通过。原矩阵 26 passed、原红测 1 failed、27 raw facts 和四份 native traces 保留；ZIP CRC、输入绑定与两份外部完整归档复制核对通过。SIGTERM 请求、清理 SIGKILL 与 native exit 143 的来源区别保留。

本轮没有新的 Browser、ATS 或模型执行。生产关闭发起方未知，生产恢复仍未验证。本审查包由 [evidence-hashes.json](evidence-hashes.json)保存新增证据。封存后需复跑测试时，先复制到全新同层目录；[verify_review.py](verify_review.py)使用 `python -B` 只向 stdout 打印只读核对结果，输出应保存到包外。

Standards：本次差异 0 项，0 项启发式问题。Spec：本次差异 0 项，0 scope creep。归档子目录边界另列为旧基准保留限制。
