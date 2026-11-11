# 创建绑定目录身份的后续修复

2026-10-12，Europe/Zurich。已修复[独立审查中的 P2](../application-worker-targetclosed-rerun-identity-review-2026-10-12/README.md)。本轮仅新增此后续包和包外封存后收据。旧包、私有证据及 04、06 closed 状态保持原状。[请求](request.md)、[范围](review-scope.json)和 [差异](review.diff)保留固定输入。

后续使用本包的 [rerun.py](rerun.py)。保护范围包含九个旧包及入口自身。最近的 identity-fix 和 identity-review 均已纳入保护。

## 创建和归档绑定

入口保留单次输出解析、叶子链接拒绝、后代路径与文件系统身份检查。通过后从根目录逐层打开父目录，使用原生 `O_DIRECTORY | O_NOFOLLOW`。每个打开的目录描述符通过 `fstat` 与保护根的设备号／inode 比较，再用于相对创建。

| 操作 | 身份约束 |
| --- | --- |
| 打开既存父目录 | `os.open(name, flags, dir_fd=parent)`，不跟随插入的链接 |
| 创建缺失父目录 | `os.mkdir(name, dir_fd=parent)`，使用已核验的父目录描述符；并发插入链接时拒绝已有名称 |
| 创建输出及 cases | 相对已核验描述符创建；输出描述符保留至归档结束 |
| 后续归档写入 | `os.fchdir(output_fd)` 后使用相对路径；父路径替换不会改变当前工作目录的目录身份 |
| 退出或异常 | `ExitStack` 恢复原工作目录并关闭持有的描述符 |

入口进程在一次归档期间持有工作目录作用域。此入口用于 CLI，不在同一进程中并行调用 `main`。原 pytest 驱动及子进程继承此工作目录；原测试和 probe 文件没有修改。`reserve_output` 保留返回普通路径的兼容接口；实际 CLI 使用保留描述符的归档作用域。

[原生能力记录](native-capabilities.json)确认本机 Python 3.13.14 的 `open/mkdir dir_fd`、`O_NOFOLLOW` 和 `fchdir` 可用。没有新增依赖。原时限、诊断断言、附件复制及失败时的外部原件保留逻辑不变。

## 回归

| 记录 | 结果 | 说明 |
| --- | --- | --- |
| [修复前日志](before.log) / [XML](before.xml) | 12 failed | 两种父目录竞态及预留后归档写入重定向；仅操作合成临时根 |
| [首次实现日志](first-green.log) / [XML](first-green.xml) | 130 passed，6 failed | 新 12 项通过；旧保护根断言、创建 hook 和模拟身份尚未迁移 |
| [迁移后日志](second-green.log) / [XML](second-green.xml) | 152 passed | 增加两类最新封存包的后代拒绝，并迁移原创建 hook |
| [最终日志](offline-final.log) / [XML](offline-final.xml) | **166 passed，0 failed / error / skipped** | 原 124 项加本轮 42 项，轮次不相加 |
| [实际 CLI 检查](preseal-cli-check.json) | **40 次拒绝，exit 2** | 十个根、正常／大写拼写、空／重复前缀；两种 mkdir spy 先确认安全 |
| [Ruff check](ruff-final-check.log) / [format](ruff-final-format.log) | 通过 | 本轮八份 Python 文件 |

新 [42 项回归](test_directory_identity.py)包含：16 项最新包后代拒绝；8 项创建前的缺失父链接插入／既存父目录替换；4 项预留后的归档写入；8 项打开父目录前的链接变化；4 项新父目录打开后的替换；2 项描述符关闭与工作目录恢复。

缺失父链接在创建前插入时，入口返回 2，suite 不执行。既存父目录在打开后被替换时，创建和全部归档仍留在原目录。新父目录打开后再被替换时，也保持打开的目录身份。每项均核对合成保护根字节及目录树不变。

原 35 项归档回归为[字节一致副本](test_rerun_archive.py)。原父包回归仅增加两类保护根的集合断言。原路径身份回归把 mkdir hook 迁移到 `os.mkdir`；模拟大小写敏感身份同时覆盖 `stat` 与 `fstat`。断言继续检查拒绝、归档位置和旧文件不变。大小写敏感卷的原生验收仍未执行。

[原输入哈希](successor-inputs.json)、[原源码](before-sources)、[修复前新回归](test_directory_identity.red-executed.py.txt)、[首次实现源码](first-implementation-sources)和 [第二次实现源码](second-implementation-sources)均保留。首次 import 排序问题已在新回归文件中修正；原封存源码未格式化或修改。

## 原生诊断

工作目录作用域改变了子进程的归档寻址，因此另通过此入口运行原合成套件。

| 原套件 | 结果 | 证据 |
| --- | --- | --- |
| 原矩阵 | **26 passed** | [日志](runs/native-matrix/pytest.log)、[XML](runs/native-matrix/pytest.xml) |
| 原历史红测 | **1 failed，exit 1** | [日志](runs/native-red/pytest.log)、[XML](runs/native-red/pytest.xml)；原 timer 传播断言保留 |

[原生附件核对](native-evidence-audit.json)确认 27 raw facts、四份 native traces、ZIP CRC、原始 facts 与 case 对应、当前输入绑定及附件保存后的 child 工作区清理。原红测没有改为通过。

原生输出先保存到全新 `/tmp` 目录，再独占复制到 [runs](runs)。[全量复制核对](native-copy-audit.json)确认所有路径、字节与链接目标一致。两个外部完整归档继续保留。

## 保留和后续使用

[保留核对](preservation-audit.json)确认 **2692 个旧公开文件哈希、九个旧包文件集、目录树及链接目标不变**。两个最新旧 manifest 有效。私有原证据字节／元数据及私有诊断包不变。04、06 保持 closed。旧原生 facts 和 traces 的只读核对继续通过。

本轮原生执行只验证合成诊断和目录绑定。SIGTERM 请求、后续清理 SIGKILL 与 native exit 143 保留原有来源区别。生产发起方未知，生产恢复仍未验证。

本包由 [evidence-hashes.json](evidence-hashes.json)封存。封存后 CLI 拒绝、旧包保留及自身 manifest 核对另保存到[包外收据](../application-worker-targetclosed-rerun-dirfd-fix-postseal-check-2026-10-12.json)。封存后不要在此目录直接复跑测试；TMPDIR 回归会在源码父目录创建临时目录。需复跑时，先把入口和四份 `test_*.py` 字节复制到全新同层目录，并指定全新 `/tmp` basetemp 与 cache_dir。

从仓库根运行以下命令，将 UNIQUE 替换为新值：

```bash
UV_CACHE_DIR=/tmp/tomorrowstar-rerun-uv-cache uv run --locked python -B \
  .scratch/application-worker-targetclosed-rerun-dirfd-fix-2026-10-12/rerun.py \
  --suite matrix --output /tmp/targetclosed-dirfd-UNIQUE-run/archive
```

[verify_preservation.py](verify_preservation.py)、[check_protection.py](check_protection.py)和 [audit_native.py](audit_native.py)使用 `python -B` 只向 stdout 打印核对结果。输出应保存到包外。
