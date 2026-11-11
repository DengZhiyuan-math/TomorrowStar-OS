# 子目录身份绑定后续修复包 — 2026-10-12

修复 `cases` 与 `child-artifacts` 的链接替换重定向。所有变更只在本后续包。原封存包、私有证据与 04、06 closed 状态保持不变。生产恢复未验证。

`rerun.py` 保留父目录逐层 `dir_fd` 校验和归档根的工作目录绑定。它增加一个受限的 `Path` 适配器。适配器保留已核验目录的描述符，并用 `mkdir(..., dir_fd=...)`、`open(..., O_NOFOLLOW, dir_fd=...)` 和 `symlink(..., dir_fd=...)` 执行旧写入器使用的操作。`cases`、每个 case、`matrix`、`child-artifacts` 和附件嵌套目录都使用该机制。目录打开后即保留其描述符，后续写入不重新解析它的路径。

打开前出现的目录链接会被拒绝。打开后路径被链接替换时，写入继续落在原已打开的目录。文件打开也设置 `O_NOFOLLOW`。源 probe 直接使用原封存源路径；归档中的源链接仍保留。原诊断源码、断言、20 秒子进程超时和原始 facts/trace 字节未修改。

Pytest 的 XML 与缓存先写入本次拥有的外部临时目录，再通过同一个适配器导入归档。临时目录不受 `TMPDIR` 或 `tempfile.tempdir` 重定向。测试结束时关闭 case 描述符。归档上下文退出时关闭剩余描述符并恢复原工作目录。已关闭的绑定不能通过被复用的描述符写入。若套件或归档抛出异常，保留外部原始文件和已写入的定位信息。

| 检查 | 结果 |
| --- | --- |
| 同一个公开调用复现，旧入口 | 8/8 失败，均向合成封存目录新增文件 |
| 同一个公开调用复现，新入口 | 8/8 通过 |
| 联合离线回归 | 255 passed；166 项既有回归 + 89 项新增回归 |
| 目录替换回归 | 两类子目录；创建前、打开前、打开后、连续写入间；含 case、matrix 与附件嵌套父目录 |
| 实际 CLI 静态保护 | 48/48 拒绝；12 个保护根 × 正常/大写拼写 × 空/重复前缀 |
| 原生合成矩阵 | 26 passed |
| 原生历史红色诊断 | 1 项预期失败；历史断言未改 |
| 新原生证据完整性 | 27 份原始 facts、4 份 native trace；facts 对应、ZIP CRC 和输入绑定均通过 |
| 外部归档完整复制 | 两份归档的目录项、文件字节和 81 个源链接目标全部相同 |
| 旧证据保留 | 3013 个旧公共哈希、11 个旧包文件集、完整目录树及链接目标均不变 |
| 私有证据 | 原字节、元数据、私有诊断包不变；只保存聚合校验结果 |
| 工单 | 04 closed；06 closed |
| 生产恢复 | 未验证 |

`successor.diff` 给出相对 dirfd-fix 的变更。旧四个回归模块保留原行为断言。两个模块字节不变；另外两个只补充合成 request 的关闭生命周期与最新保护根集合断言。`regression-copy-audit.json` 记录这些差异。

回归证据见 `offline-final.log`、`offline-final.xml` 和 `validation-summary.json`。`retained-repro-red.log` 与 `retained-repro-green.log` 使用同一个测试文件，分别加载冻结旧入口与新入口。最初的红色见证另存为 `descendant-red.py.executed.txt`；它不会进入默认测试收集。中间失败与格式检查日志保留原样，不改写为通过。

原生完整归档见 `runs/native-matrix` 和 `runs/native-red`。外部原件保留在 `/private/tmp/targetclosed-subdirs-native-{matrix,red}-20261012-run1/archive`。`native-copy-audit.json`、`native-audit.json` 与 `preservation-final.json` 分别记录完整复制、原生证据和旧证据校验。

封存前执行的联合命令：

```sh
UV_CACHE_DIR=/tmp/tomorrowstar-subdirs-uv-cache-20261012 uv run --locked python -B scripts/run_pytest.py -q .scratch/application-worker-targetclosed-rerun-subdirs-fix-2026-10-12 -o cache_dir=/tmp/tomorrowstar-subdirs-final-folder-cache --junitxml=/tmp/tomorrowstar-subdirs-final-offline-20261012.xml
```

封存后不得在本包内重跑离线测试。旧回归中的 TMPDIR 反例会在测试副本目录创建临时子目录。后续回归需使用新的同级未封存副本，并将本包纳入副本的保护根。入口 `python -B rerun.py --output <新的外部目录>` 可产生新的合成归档。它不等于生产恢复验收。

`evidence-hashes.json` 封存本包所有文件和源链接所指字节。自身清单不纳入自身哈希。封存后检查写入包外的 `../application-worker-targetclosed-rerun-subdirs-fix-postseal-check-2026-10-12.json`。该回执包含包自身封存校验、旧证据保留、48 条实际 CLI 拒绝与原生归档核验。
