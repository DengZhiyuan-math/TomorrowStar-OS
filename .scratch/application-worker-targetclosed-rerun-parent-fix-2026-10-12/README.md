# 封存父包保护的后续修复

2026-10-12，Europe/Zurich。已修复[前轮 P2](../application-worker-targetclosed-rerun-review-2026-10-12/README.md)指出的已封存父包遗漏。本轮仅新增此后续包。原修复包、诊断与审查包、稳定性验收与失败记录保持原状；04、06 保持 closed。

## 入口与保护范围

后续复验统一使用本包的 [rerun.py](rerun.py)。原入口保留为历史输入。新版仅在原 `PROTECTED_ROOTS` 增加三个根：已封存原修复包、其独立审查包，以及入口自身所在目录。总计五个旧包及入口自身受到保护。

路径解析后匹配任何保护根时，入口在 mkdir 和 suite 执行前拒绝输出。新叶子、深层后代、符号链接父路径及 `..` 路径均受此边界约束。入口自身目录始终受保护，封存前后行为一致。代码没有增加依赖，原诊断时限与断言保持原样。

初次联合复验后的补充探针发现 `sealed/new-parent/../../fresh` 的特殊路径：输出解析到包外，但原 lexical mkdir 会先向封存包增加中间目录。该[合成观测](dotdot-probe-before.json)、[两项修复前失败](dotdot-before.log)及[初次 Spec 发现](spec-initial.md)保留。最终入口对通过检查的解析路径执行 mkdir，不再经过未解析的中间目录；原 dangling-link 拒绝规则保持。

最终改动保留原 guard，并只在通过后增加一行 `path = path.resolve()`。代理提出的叶子链接异常假设在锁定运行时未复现：[修正前兼容检查](symlink-before.log)为 1 passed。[假设与复核记录](standards-symlink-followup.md)保留，该项没有被记为已复现缺陷。

必须指定保护包之外的全新输出目录。默认前缀为空；同一前缀可在两个全新目录中使用。已有目录、文件、符号链接和重复用例继续拒绝。示例从仓库根运行：

```bash
uv run --locked python -B .scratch/application-worker-targetclosed-rerun-parent-fix-2026-10-12/rerun.py \
  --suite matrix --output /tmp/targetclosed-UNIQUE-run/matrix
```

将 UNIQUE 替换为新值。不要直接运行原矩阵或原红测驱动；它们的历史写路径保持原样。入口插件只重定向归档 ROOT，执行原 suite 与原 probe。

本轮实际输出位于新 `/tmp` 父目录。运行完成后，使用独占新目录将归档复制到 [runs](runs)。[最终复制核对](native-copy-audit-sealed.json)确认全量文件字节与链接目标一致；外部完整归档也保留。runner 的 child 临时工作区在附件保存后清理。

## 回归与执行结果

原 [35 项回归](test_rerun_archive.py)为字节一致副本；复制来源及哈希见 [successor-inputs.json](successor-inputs.json)。[新增 36 项](test_sealed_parent.py)覆盖三个新增保护根的默认／重复前缀，直接子目录、深层后代、链接父路径和 `..` 路径，真实 CLI 拒绝、同前缀新兄弟目录、部分归档失败时 facts/trace 与定位文件保留、解析到包外的 `..` 路径，以及自引用叶子链接兼容。

封存后复跑离线回归，先把源码字节复制到新的同层未封存目录。原 35 项中的 TMPDIR 用例会在源码父目录创建临时目录。本轮所有回归均在封存前执行。

| 记录 | 结果 | 含义 |
| --- | --- | --- |
| [修复前合成父包回归](sealed-parent-before.log) / [XML](sealed-parent-before.xml) | 25 failed，7 deselected | 原入口副本缺少三个根；只写临时合成父包，真实旧包没有执行危险路径 |
| [第一次联合回归](offline-final.log) | 67 passed | 原 35 项与新增 32 项通过 |
| [增加部分归档失败回归](offline-complete.log) | 68 passed | 新增中途复制失败的原始副本保留断言 |
| [首次源码联合回归](offline-pinned.log) / [XML](offline-pinned.xml) | 68 passed，0 failed / error / skipped | 加根后的第一轮；[源码快照](phase-1-sources)、[范围](review-scope.json.first)保留 |
| [初次原生矩阵](runs/native-matrix/pytest.log)、[红测](runs/native-red/pytest.log) | 26 passed / 1 failed | 对应首次源码；后续没有覆写 |
| [解析路径修复前回归](dotdot-before.log) / [XML](dotdot-before.xml) | 2 failed，33 deselected | 直接路径与链接父路径均会创建封存中间目录；只操作合成包 |
| [第二版源码联合回归](offline-canonical.log) / [XML](offline-canonical.xml) | 70 passed，0 failed / error / skipped | [第二版源码快照](phase-2-sources)保留 |
| [第二版矩阵](runs/native-matrix-final/pytest.log)、[红测](runs/native-red-final/pytest.log) | 26 passed / 1 failed | 第二版源码绑定；后续没有覆写 |
| [最终源码联合回归](offline-sealed.log) / [XML](offline-sealed.xml) | 71 passed，0 failed / error / skipped | 35 既有 + 36 新增；轮次不相加 |
| [最终原生矩阵](runs/native-matrix-sealed/pytest.log) / [XML](runs/native-matrix-sealed/pytest.xml) | 26 passed | 原诊断矩阵复验，包含预期故障签名 |
| [最终历史原红测](runs/native-red-sealed/pytest.log) / [XML](runs/native-red-sealed/pytest.xml) | 1 failed，exit 1 | 原断言继续揭示历史 timer 传播缺陷；不改为通过 |

[修复前入口](rerun.before.py.txt)及新回归在 import 格式修正前的[执行源码](test_sealed_parent.executed-before-import-format.py.txt)保留。[首次 Ruff 失败摘要](ruff-first.log)、[核对脚本长行失败](ruff-complete.log)及后续 [check](ruff-canonical.log)、[format](ruff-format-canonical.log)保留。格式修正没有改断言。原诊断的 child 超时 20 秒、250 ms timer、crash 事件 1500 ms 等待和红测断言保持封存哈希一致。

超时回归保留原 TimeoutExpired、命令、20 秒预算、原始 stdout/stderr 和部分 facts/trace。归档中途失败时，已复制 facts、部分 trace、外部完整副本及定位文件均保留；不写通过 result。TMPDIR 与 tempfile.tempdir 不改变明确的 `/tmp` child 工作区选址。

## 保留与信号证据

[最终核对](preservation-and-evidence-audit-sealed.json)确认 1840 个旧公开文件哈希及五个旧包的文件集均无变化，文件集包含符号链接。私有原证据的字节／元数据和私有诊断包哈希保持原状。04、06 保持 closed。基线见 [旧哈希](protected-before.json)与[旧文件集](protected-file-sets-before.json)。[只读核对脚本](verify_evidence.py)向 stdout 打印结果，不写证据文件。

矩阵保存 26 raw facts / 3 native traces，红测保存 1 raw facts / 1 native trace。四份 ZIP 的 CRC 通过。原始 facts 与用例 JSON 匹配；红测的两份 trace 字节一致。矩阵驱动不另复制 trace 到 case 目录，该项为 null。全量归档复制核对另确认 raw trace 的字节一致，执行输入绑定保持当前。

本轮六份 SIGTERM 合成材料仍区分三个来源：

| 结论 | 支持证据 |
| --- | --- |
| 初始 SIGTERM 请求 | 封存 probe 的 requested_signal、owned_browser_pid 与 os.kill 调用；stderr 没有独立初始 SIGTERM 记录 |
| 后续清理 SIGKILL | 对每份发生 SIGKILL 的材料，核对同 PID stderr 的 gracefully close → kill → will force kill → native signal=SIGKILL；固定 SDK 的 process.kill 清理源码哈希匹配 |
| native exitCode=143 | 另有以 143 退出的材料，逐项记录其 cleanup 行是否存在。Browser 退出码与 worker returncode=2 含义不同 |

这些记录说明受控执行路径的顺序。生产关闭发起方仍未知，生产恢复仍未验证。合成通过不会改变历史生产结论或 04、06 的原关闭依据。

## 后续审查

最终固定范围见 [request.md](request.md)、[review-scope-final.json](review-scope-final.json)和 [review-final.diff](review-final.diff)。首次 [范围](review-scope.json)和 [diff](review.diff)保留。独立 Standards 与 Spec 报告在核对完成后追加。原修复及审查结论全部保留。
