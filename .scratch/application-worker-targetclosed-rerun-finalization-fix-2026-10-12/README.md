# 最终化清理后续修复包 — 2026-10-12

修复 subdirs-review 记录的继承限制。只新增此后续包和包外封存后回执。旧封存包、私有证据及 04、06 closed 状态不变。生产恢复未验证。

`rerun.py` 将 `shutil.rmtree(temporary)` 移到最终输入核验和 `write_json(result.json, ...)` 返回之后，并要求 `inputs_unchanged` 为 true。目录身份绑定、独占输出、子目录和文件的 `O_NOFOLLOW`、原诊断源码、断言及 20 秒子进程预算均保留。

| 最终化状态 | 临时目录 | 定位信息 |
| --- | --- | --- |
| 输入匹配，result.json 写入并关闭成功 | 随后删除 | 保留历史 temporary-workspace.json 记录 |
| 最终输入读取异常 | 保留完整外部原件 | temporary-workspace.json 指向仍存在的目录 |
| 最终输入不匹配 | 保留完整外部原件；result 的 exit_code 为 2 | 定位仍有效 |
| result.json 被占用/链接拒绝、部分写入或关闭异常 | 保留完整外部原件 | 定位仍有效 |
| 套件或附件归档抛出异常 | 继续保留外部原件 | 使用此前写入的定位记录 |

清理门槛是最终化成功。完成的 pytest 调用返回 1 或 2，仍可在输入匹配且 result 完整写入后清理。历史红色诊断的预期失败不被改为通过。若 result 写入中断，可能留有不完整 result；它不触发清理，独立的定位记录和外部原件继续保留。

| 验证 | 结果 |
| --- | --- |
| 首个真实 result 链接失败 | 旧行为红色，新实现绿色 |
| 输入哈希不匹配 | 首次移动清理后仍为红色；补充匹配门槛后绿色 |
| 同一 6 项失败回归，冻结旧入口 | 6 failed；仅合成外部原件的保留断言失败 |
| 新入口联合回归 | 280 passed；255 项既有 + 25 项新增 |
| 新增行为覆盖 | 6 项最终化失败保留、3 项成功清理顺序、16 项最新封存包保护 |
| 实际 CLI 拒绝 | 56/56；14 根 × 正常/大写 × 空/重复前缀 |
| 保留失败见证 | 3 个实际存在的外部工作目录；输入异常、输入不匹配、result 链接拒绝 |
| 原生合成矩阵 | 26 passed |
| 原生历史红测 | 1 项预期失败、exit 1；最终化成功后清理 |
| 原生证据完整性 | 27 raw facts、4 native traces；事实对应、ZIP CRC、当前输入绑定均通过 |
| 原生完整复制 | 目录项、132 个普通文件字节和 81 个源链接目标全部匹配 |
| 旧证据保留 | 3353 个旧公共哈希、13 个旧包文件集、目录树与链接目标不变 |
| 私有证据与工单 | 私有原字节/元数据和诊断包不变；04 closed、06 closed |
| 生产恢复 | 未验证 |

回归通过公开 `main` 执行实际文件操作。子套件用合成输出替代浏览器执行。输入读失败/不匹配仅在文件系统读取边界注入，不修改任何真实输入。result 链接使用真实文件系统拒绝；部分写入及关闭错误在流边界注入。测试核对外部 facts、trace、XML 和缓存字节、定位的 owner_pid/synthetic、保护根完整树、目录 open/dup 的关闭及 cwd 恢复。

`test_finalization.py` 是新 25 项回归。`successor.diff` 固定相对 subdirs-fix 的改动。旧六个测试模块中五个字节不变；`test_sealed_parent.py` 只补充两个最新包的集合断言。入口同时增加 subdirs-fix、subdirs-review 保护根。`regression-copy-audit.json` 保留全部哈希与差异。

红绿日志和每个阶段的执行源码保留原样。`before-rerun.py.txt` 是冻结旧入口。`test_finalization.first-red.py.txt`、`rerun.first-green.py.txt`、`test_finalization.mismatch-red.py.txt` 和 `rerun.mismatch-green.py.txt` 记录逐项修复。`baseline-failure-replay.log` 保存最终同一失败回归在旧入口的结果。`offline-final.log/xml` 和 `validation-summary.json` 固定最终计数；早期轮次不相加。

`retained-failure-witnesses-final.json` 固定最终三个失败归档、外部工作目录和有效定位文件的路径。原件保留在 /tmp，封存前后均逐字节核对。首次见证和其执行源码也原样保留，不累加轮次。它们是合成见证，没有浏览器/ATS/模型调用。原生完整归档见 `runs/native-matrix`、`runs/native-red`；外部完整原件在 `/private/tmp/targetclosed-finalization-native-{matrix,red}-20261012-run1/archive`，同样保留。

`preservation-final.json` 校验所有旧公共哈希、文件集、完整树、链接目标和私有聚合状态。未复制私有内容、路径或指纹。`evidence-hashes.json` 封存本包文件与源链接所指字节；自身清单不纳入自身哈希。封存后回执在 `../application-worker-targetclosed-rerun-finalization-fix-postseal-check-2026-10-12.json`。

封存前实际联合命令：

```sh
UV_CACHE_DIR=/tmp/tomorrowstar-finalization-uv-cache-20261012 uv run --locked python -B scripts/run_pytest.py -q .scratch/application-worker-targetclosed-rerun-finalization-fix-2026-10-12 -o cache_dir=/tmp/tomorrowstar-finalization-final-offline-cache --junitxml=/tmp/tomorrowstar-finalization-final-offline-20261012.xml
```

封存后不要在本包内复跑测试。TMPDIR 反例会在源码副本目录创建临时子目录。后续测试需使用新的同级未封存副本，并将本包加入副本保护根。入口 `python -B rerun.py --output <全新外部目录>` 可生成新合成归档；它不是生产恢复验证。
