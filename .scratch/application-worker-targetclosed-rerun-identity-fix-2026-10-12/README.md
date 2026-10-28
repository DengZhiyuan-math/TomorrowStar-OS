# 路径身份与单次解析修复

2026-10-12，Europe/Zurich。修复[独立审查](../application-worker-targetclosed-rerun-parent-review-2026-10-12/README.md)中的两项 P2。本轮只新增此后续包及包外的封存后检查收据。旧入口和旧证据保留。

后续复验使用本包的 [rerun.py](rerun.py)。保护范围包含七个旧包和入口自身。最新父包修复与独立审查也在保护范围内。

## 实现

| 缺陷 | 修复 | 验证 |
| --- | --- | --- |
| APFS 大小写别名不匹配字符串路径 | 保留路径后代判断，再用现存祖先的 `Path.samefile()` 核对文件系统身份 | 六个合成根、两种前缀、直接与深层输出，共 24 项本机别名回归；没有到达 mkdir |
| 父链接在检查后改指，创建目标变化 | 叶子链接先拒绝；原输出只解析一次；检查和 mkdir 使用同一解析结果 | 旧根与自身根、两种前缀、解析前／检查后／mkdir 前改指，共 12 项回归 |

`samefile()` 按文件系统身份判断，没有统一转小写。大小写不同且身份不同的目录允许创建；此项使用模拟身份检查。本轮没有运行大小写敏感卷原生验收。`..`、叶子链接、现存输出和独占创建规则继续由原回归覆盖。

本轮没有新增依赖。归档、附件保存、异常处理、原 20 秒 child 时限及原诊断断言不变。[review.diff](review.diff)和 [review-scope.json](review-scope.json)固定改动范围。

## 回归证据

| 记录 | 结果 | 说明 |
| --- | --- | --- |
| [修复前日志](before.log) / [XML](before.xml) | 28 failed，9 deselected | 24 项别名和 4 项检查后改指准确触发旧缺陷；只操作临时合成根 |
| [初次修复日志](after.log) / [XML](after.xml) | 148 passed | import 导入的原测试又被收集了 24 次；首次执行源码保存在 [first-green-sources](first-green-sources) |
| [最终日志](offline-final.log) / [XML](offline-final.xml) | **124 passed，0 failed / error / skipped** | 消除重复收集后：原 71 项，加本轮 53 项；轮次不相加 |
| [实际 CLI 检查](preseal-cli-check.json) | **32 次拒绝，exit 2** | 八个根、正常／大写拼写、两种前缀；先用 mkdir spy 证明安全，再运行实际 CLI；没有创建输出 |
| [最终 Ruff check](ruff-final-check.log) / [format](ruff-final-format.log) | 通过 | 检查全部六个本轮 Python 文件 |

原 [35 项归档回归](test_rerun_archive.py)为字节一致副本。原 [36 项父包回归](test_sealed_parent.py)仅在保护根集合断言中增加两个最新旧包。旧回归源码及 [输入哈希](successor-inputs.json)保留。新增 [53 项回归](test_path_identity.py)复用既有父包检查，不复制其实现。修复前执行的新增源码另保存在 [test_path_identity.red-executed.py.txt](test_path_identity.red-executed.py.txt)。

初次 uv 调用因默认缓存目录无写权限而未执行测试；[环境日志](before-environment.log)保留。后续使用明确的 `/tmp` uv 缓存，执行 `uv run --locked`。

## 保留核对

[保留核对](preservation-audit.json)确认 **2609 个旧公开文件哈希、七个旧包文件集及链接目标不变**，包含前轮 2552 个哈希。目录树另从本轮实际 CLI 检查前固定，检查后无变化。两个旧封存 manifest 继续有效。私有原证据字节／元数据和私有诊断包不变；04、06 仍为 closed。

[旧原生证据实时只读核对](previous-evidence-live-audit.json)通过。原矩阵 26 passed、原红测 1 failed、27 raw facts 和四份 native traces 保留。原红测没有改为通过。本轮新增 Browser 执行为零。生产发起方未知，生产恢复仍未验证。

本包由 [evidence-hashes.json](evidence-hashes.json)封存。封存后实际 CLI 拒绝与最终保留核对记录在[包外收据](../application-worker-targetclosed-rerun-identity-fix-postseal-check-2026-10-12.json)，不向本包追加结果。

## 后续使用

从仓库根使用明确的全新包外目录。将 UNIQUE 替换为新值。

```bash
UV_CACHE_DIR=/tmp/tomorrowstar-rerun-uv-cache uv run --locked python -B \
  .scratch/application-worker-targetclosed-rerun-identity-fix-2026-10-12/rerun.py \
  --suite matrix --output /tmp/targetclosed-UNIQUE-run/matrix
```

不要从封存源码目录直接复跑测试；原 TMPDIR 回归会在源码父目录创建临时目录。需要复跑时，将 `rerun.py` 和三个 `test_*.py` 文件字节复制到 `.scratch/` 下的全新同层目录，再从仓库根通过 `scripts/run_pytest.py` 执行，指定全新的 `/tmp` basetemp 与 cache_dir。

[verify_preservation.py](verify_preservation.py)和 [check_protection.py](check_protection.py)只向 stdout 打印检查结果。检查时使用 `python -B`，并将输出保存到封存包之外。
