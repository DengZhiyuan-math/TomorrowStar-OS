# TargetClosedError 复验归档修复

2026-10-12，Europe/Zurich。范围是[独立审查发现的两条覆写路径](../application-worker-targetclosed-review-2026-10-12/README.md)。原诊断包、审查包、验收、失败记录及 04、06 保持原状。

**后续复验使用新入口 [rerun.py](rerun.py)。** 它要求不存在的输出目录，并拒绝已有目录、文件和符号链接。没有修改原测试、探针、断言、250 ms timer、crash 事件等待或命令预算。没有增加依赖。

## 使用与保存边界

从仓库根目录执行。每次指定一个不存在的新目录：

```sh
UV_CACHE_DIR="$PWD/.cache/uv" uv run --locked python -B \
  .scratch/application-worker-targetclosed-rerun-fix-2026-10-12/rerun.py \
  --output /private/tmp/targetclosed-matrix-NEW
```

原红测使用另一个新目录；原失败断言应继续失败，返回码仍为 1：

```sh
UV_CACHE_DIR="$PWD/.cache/uv" uv run --locked python -B \
  .scratch/application-worker-targetclosed-rerun-fix-2026-10-12/rerun.py \
  --suite red --prefix repeat- \
  --output /private/tmp/targetclosed-red-NEW
```

`--output` 无默认值。默认前缀为空，并覆盖环境中的旧前缀。前缀只允许字母、数字、下划线、点和连字符。相同前缀可以用于不同的新目录；同一目录不能复用。已有空目录、失败后的目录、悬空链接也被拒绝。原封存包内部不能作为新输出位置。

新入口复用 checkout pytest launcher。pytest 原生 fixture 将原测试的 ROOT 定向到独占创建的用例目录。探针与保留 main 使用只读来源链接，保持原源码位置的 checkout import 解析。每个用例目录也拒绝复用，检查在旧保存函数或子进程调用之前完成。插件另核对归档属于本次入口进程。

pytest.log、invocation.json 和 result.json 使用独占创建。XML、cache 和用例附件位于本次新归档。worker 临时工作区由标准库在明确选定的 `/tmp` 创建，忽略 TMPDIR 和 tempfile.tempdir 的 checkout 内覆盖；原隐私守卫不变。禁止字节码写入，避免向原诊断目录增加缓存文件。

清理前，将 worker 临时工作区生成的 facts.json 和 native-trace.zip 按原始字节复制到本次 child-artifacts 目录；部分或无效附件不补造完成结论。原 20 秒子进程超时还会保留异常携带的 stdout、stderr、命令及原预算。附件保存失败时不删除外部临时工作区，唯一副本及 temporary-workspace.json 定位记录保留。正常保存后仅清理本次拥有的临时工作区。

原危险入口仅作为历史源码保留。后续复验按本页的新入口执行。新入口不把非零返回码改成通过，不把合成诊断当生产恢复验收。

## 回归及执行证据

| 轮次 | 结果 | 含义 |
| --- | --- | --- |
| [旧保存函数红测](legacy-red.log) / [XML](legacy-red.xml) | 2 failed | 临时合成附件复现两条覆写路径；没有写原归档 |
| [首轮离线回归](offline-first.log) / [XML](offline-first.xml) | 22 passed | 默认前缀、重复前缀、重复执行及路径边界 |
| [进程绑定回归](offline-final.log) / [XML](offline-final.xml) | 25 passed | 加入缺失归档或其他进程归档的拒绝路径 |
| [首轮原生矩阵](runs/native-matrix-default/pytest.log) / [XML](runs/native-matrix-default/pytest.xml) | 23 passed / 3 failed | 新入口错误地把临时 worker 工作区放进 checkout，原隐私守卫拒绝了三个历史入口用例 |
| [修正目录后的离线回归](offline-after-native.log) / [XML](offline-after-native.xml) | 26 passed | 当前环境下的 checkout 外临时工作区及保存边界 |
| [修正目录后的原生矩阵](runs/native-matrix-final/pytest.log) / [XML](runs/native-matrix-final/pytest.xml) | 26 passed | 原诊断断言通过；首轮审查发现矩阵 trace 未保存，不能作为完整归档验收 |
| [首个新目录中的原红测](runs/native-red-final/pytest.log) / [XML](runs/native-red-final/pytest.xml) | 1 failed，符合原失败断言 | 新 stderr、facts、red trace 留存，不转成修复通过 |
| [已有归档 CLI 拒绝](repeated-cli-regression.json) | 3 项通过 | 默认前缀、变更前缀、重复前缀均不能复用归档；没有新增 Browser 执行 |
| [补齐首轮审查后的离线回归](offline-post-review.log) / [XML](offline-post-review.xml) | 35 passed | 补 TMPDIR / tempfile.tempdir、附件保存、20 秒超时流及归档失败唯一副本回归 |
| [最终离线回归](offline-complete.log) / [XML](offline-complete.xml) | 35 passed | 再核对归档失败的外部唯一副本定位记录；执行输入不变 |
| [最终原生矩阵](runs/native-matrix-complete/pytest.log) / [XML](runs/native-matrix-complete/pytest.xml) | 26 passed | 原断言和时限不变；26 份子进程 facts 和 3 份保留入口 native trace 另存 |
| [最终新目录中的原红测](runs/native-red-complete/pytest.log) / [XML](runs/native-red-complete/pytest.xml) | 1 failed，符合原失败断言 | 同时保留原红测附件及 child-artifacts 中原始 facts/trace；不转成生产恢复通过 |

不合并重复轮次的通过数。首轮源文件、哈希及原生失败对应的入口源码另存。首次原生失败的目录、stderr 和 XML 不改写。修正只影响新入口的临时目录位置，未放宽原隐私守卫或原断言。

离线回归实际调用 AST 提取的原保存函数，并用假子进程及临时合成哨兵检查旧文件不变。原生复验运行原测试与原探针。默认前缀、同一用例重复执行、同一目录重复执行、同前缀的新目录历史保留均覆盖。

## SIGTERM 与清理 SIGKILL 的来源澄清

此说明是原诊断 README 第 64 行的新增澄清。原文及原始流不改写。

| 信息 | 直接来源 | 可支持的结论 |
| --- | --- | --- |
| 初始 SIGTERM 请求 | [probe_minimal.py:58](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-targetclosed-2026-10-12/probe_minimal.py:58>)的 requested_signal 字段及第 59 行 os.kill；facts 中的 owned_browser_pid | 此受控探针调用了发信号路径。stderr 没有独立的初始 SIGTERM 记录 |
| 清理阶段 SIGKILL | 同一 PID 的原始 stderr：graceful close → kill → will force kill → native signal=SIGKILL；固定 SDK 清理源码的 process.kill | 此受控试验的最终 SIGKILL 出现在清理路径之后。它不能反推历史生产的发起信号 |
| Browser exitCode=143 | 同一 PID 的原生退出行 | 这是 Browser 退出事实，不能与 worker returncode=2 混用；清理尝试与退出存在竞争 |
| 两阶段先后 | 源码、facts 与同一 PID 的 stderr 共同关联，见[既有信号核对](../application-worker-targetclosed-review-2026-10-12/signal-order-audit.json) | 不能声称 stderr 直接记录了两种信号，也不能用这个合成顺序补足原生产生命周期证据 |

原生产的关闭发起方仍未知。原日志、trace 和退出证据缺口不因新入口通过而消失。生产恢复仍未验证。真实 ATS、模型、自动上传或 Submit 未启动。

## 审查与保留

通过首轮回归后新增两轴审查：[Standards 首轮](standards-review.md)、[Spec 首轮](spec-review.md)。首轮分别发现 TMPDIR 环境覆盖和临时附件遗漏，报告及对应源码快照原样保留。修正仅影响新入口，补齐回归后再做复审，不修改原诊断结论或票状态。

[归档核对](complete-archive-audit.json)确认最终矩阵保留 26 facts / 3 traces，最终红测保留 1 facts / 1 trace，四份 native ZIP 的 CRC 均通过。两个归档均再次拒绝已有目录，附件哈希不变。最终两轮原生执行输入绑定当前入口及原来源；临时工作区在保存后正常清理。

[保留核对](preservation-check.json)确认 1193 个旧公开文件无哈希变化，三个旧目录的文件集也不变。私有原证据与私有诊断包另做核对，字节、元数据和哈希均未改写。首轮与最终审查范围分开保存；最终审查时的 README 另存，不把后加结论写进旧输入记录。

复审探针首次将 `/tmp` 与解析后的 `/private/tmp` 做字面比较，产生 false；改为比较原 command 列表后为 true。两次工具观测[分别保留](spec-probe-observations.json)，原 TimeoutExpired.cmd 未被改写。这是比较方式修正，不是新的诊断通过轮次。

## Standards

[最终独立报告](standards-review-final.md)：0 项 documented standard breach，0 项 heuristic smell。首轮 TMPDIR P2 已闭合。独占目录、输入绑定、归档顺序、原时限、原隐私守卫、旧材料及生产边界核对通过。

## Spec

[最终独立报告](spec-review-final.md)：0 项 missing/partial、0 项 scope creep、0 项 implemented wrong。首轮附件 P2 已闭合。独立核对超时对象、原 20 秒预算、原命令、原始流、附件保留及归档失败唯一副本。

仓库 Ruff、格式及 diff 检查通过。新相对链接、源码行引用及新文本 diff 检查通过。没有运行全套产品回归，因为本轮未改运行模块或共享产品合同；运行了受影响的离线回归和原生合成诊断。

04、06 仍为 closed。本轮没有修改运行模块，没有提交或推送。

Standards 最终：0 项新发现。Spec 最终：0 项新发现。
