# 申请答案库复用：固定源码核验

日期：2026-10-09。对应研究票：[核验现有答案库能否支持补充后复用与任务恢复](../.scratch/independent-application-worker/issues/01-answer-store-reuse.md)。
只研究现有接口和最小缺口。未读取或初始化实际个人存储，未运行申请 worker，未使用真实岗位。

## 结论

**首版可以调用现有 Job Apply helper，继续使用一份申请答案库。**
它已经提供问题 key、别名、scope、确认状态、敏感值保存标记、profile、历史和 session。
它没有执行填表资格判断、答案 revision、任务失效和普通答案库的并发事务。
这些缺口必须由独立 worker 的调用层补齐，不能把存储查询成功理解为允许填写。

固定基线：`neonwatty/job-apply-plugin` `370204c58b1137d08c5a7e7449538ae6447be0b9`，插件 1.1.0，[MIT](https://github.com/neonwatty/job-apply-plugin/blob/370204c58b1137d08c5a7e7449538ae6447be0b9/LICENSE)。安装目录与干净 clone 的 helper、policy、answer-memory Skill、storage contract、LICENSE 五个文件逐字节相同。

从固定插件目录执行 Python helper 是首版可用的复用路径，不依赖 Codex 浏览器。
独立程序如何安装、固定和验证该 helper 版本，仍属于 [确定独立运行时与浏览器生命周期](../.scratch/independent-application-worker/issues/04-runtime-browser-lifecycle.md) 的决定。本研究没有复制或修改上游实现。

## 可直接复用和必须补齐的边界

| 能力 | helper 实际提供 | 调用方责任 |
|---|---|---|
| 问题 key | NFKC、大小写、标点、空白规范化；按规范化问题＋canonical scope 生成 SHA-256 key | 调用 `answer-key` / `answer-find`，不重写算法；不得把文本相似当作语义等价 |
| scope | question/alias 扫描要求 scope 完全相等；fallback 按 key 取记录不重查 scope；显式 key 可与记录 scope 不一致 | 构造明确 scope 并复核返回 scope；不把 US 答案用于其他国家，不将未来 sponsorship 等同于当前工作资格 |
| 别名 | `answer-put` 保存规范化 aliases；`answer-find` 可按别名匹配 | 只存用户审查过的等价问题；检测别名冲突，不能任意挑选第一个冲突结果 |
| 状态 | `confirmed` 要求非 null 值，`missing` 禁止非 null 值；其余状态可查询 | 只有适用、已确认且满足敏感规则的答案可填写；返回 `inferred` / `missing` 不构成确认 |
| 敏感保存 | 非 null 且 `state=sensitive` 或 `sensitivity!=none` 时要求 `--remember-sensitive`；helper 生成保存同意时间 | 保存和当前使用分开；helper 不核验人类是否实际同意，不自动识别工资/签证等语义，也不 enforce 每次使用复核 |
| 更新 | `answer-put` 同 key 更新记录；`confirmedAt` / `updatedAt` 是时间字段 | 提交完整字段。省略 scope、aliases、sensitivity 会采用默认值或清空，不能当作局部 PATCH |
| 撤回 | 同 key 写 `state=missing,value=null` 可移除当前 canonical 值 | 保留问题、scope、aliases；立即停止旧值复用。无 `answer-delete`，不等同于清除全部备份或已发送值 |
| profile | `profile-get` / `profile-replace`；preferences 可合并 | profile 对象不提供事实确认或适用性 gate；避免从职业证据自动推断申请答案 |
| 历史与 session | 只存 answerKeys、pendingFields 和流程元数据；闭合输入拒绝复制值及自定义 revision 字段 | 引用需重新查找；helper 不核验 key 存在，不保存答案版本，不会因答案更新或撤回自动失效 session |
| 普通写入 | 同目录临时文件、fsync、原子 replace、POSIX 0700/0600 | 原子文件替换不防止两个 read-modify-write 丢更新。所有相关写入必须经同一串行写入者或共同锁协议 |

源代码依据：[key 规范化](https://github.com/neonwatty/job-apply-plugin/blob/370204c58b1137d08c5a7e7449538ae6447be0b9/scripts/job-apply-store.py#L134)、[lookup / put](https://github.com/neonwatty/job-apply-plugin/blob/370204c58b1137d08c5a7e7449538ae6447be0b9/scripts/job-apply-store.py#L444)、[session 输入和写入](https://github.com/neonwatty/job-apply-plugin/blob/370204c58b1137d08c5a7e7449538ae6447be0b9/scripts/job-apply-store.py#L704)、[原子替换](https://github.com/neonwatty/job-apply-plugin/blob/370204c58b1137d08c5a7e7449538ae6447be0b9/scripts/job-apply-store.py#L83)、[profile](https://github.com/neonwatty/job-apply-plugin/blob/370204c58b1137d08c5a7e7449538ae6447be0b9/scripts/job-apply-store.py#L410)。

上游使用规则来自 [answer-memory Skill](https://github.com/neonwatty/job-apply-plugin/blob/370204c58b1137d08c5a7e7449538ae6447be0b9/skills/answer-memory/SKILL.md) 和 [storage contract](https://github.com/neonwatty/job-apply-plugin/blob/370204c58b1137d08c5a7e7449538ae6447be0b9/skills/answer-memory/references/storage-contract.md)，不是 `answer-find` 的程序行为。上游默认敏感值每次使用都要复核；用户要求避免重复问同一未知问题，已经授权普通确认答案的补充和复用。敏感保存与后续适用规则由 [确定申请答案库的复用范围与更新规则](../.scratch/independent-application-worker/issues/02-answer-library-contract.md) 决定；本研究不替人解决该 HITL 决策。

特别注意显式 key：helper 不验证它是否与 question/scope 生成的 key 一致。合成验证将按 scope A 生成的 key 存成 scope B，随后查询 A 得到了 B 记录。使用现有 semantic key 时也必须核对返回记录的 scope、题目含义及状态，不能只检查“找到记录”。

`job_apply_policy.py` 另有 `fcntl.flock`，仅覆盖自己的 campaign / lease / receipt 状态。
它不锁 `profile.json` / `answers.json` / session。现有孤立 QA lease 既不是答案库锁，也不是 worker 任务锁。
[policy 锁范围](https://github.com/neonwatty/job-apply-plugin/blob/370204c58b1137d08c5a7e7449538ae6447be0b9/scripts/job_apply_policy.py#L383)

## 满足“补充一次，后续复用”的最小流程

以下是调用层建议，不是已实施功能。

1. worker 提取本次题目和明确 scope，调用 `answer-find`。
2. 命中合格记录时使用该值，不再问同一答案。未命中或需复核时创建 `pendingFields`，该岗位暂停。
3. 用户提供答案后，确认该问题、值、scope 和必要别名。普通答案用 `answer-put` 保存为 confirmed；敏感值按已决定的规则处理。
4. 继续该任务前重新查答案、岗位记录和附件版本。后续相同 scope / 等价题目命中同一记录。
5. 若题目语义、选项、范围或用户事实改变，重新核验对应项。不要因旧 key 存在而沿用失效值。

worker 私人运行状态可保存 `answerKey + answerRecordDigest`，不复制答案值。
session schema 不支持答案 revision，所以这个版本绑定应放在 worker 自己的运行元数据中。
对 helper 返回的完整记录，用现有 [canonical_json_bytes / sha256_digest](../src/career_evidence_graph/validation/hashing.py) 生成内容绑定；不再实现另一种 question key 算法。运行前重新取记录并比较，差异令既有任务准备失效。时间字段仅精确到秒，且可由输入 supplied `confirmedAt`，不能充当可靠内容 revision。

所有写入应由一个受控入口串行执行，包括门户中用户更新和 worker 保存。
只有一名 worker 不代表只有一名答案库写入者。直接同时运行现有交互插件仍可绕过新入口；
因此不能声称“新 wrapper 加锁”已经保护未采用该协议的旧 helper 调用。
具体部署与所有权须在运行时 / 输入票中明确，无需现在增加数据库。

## 合成验证

每个存储调用均显式传入新建的 `/private/tmp` root 和不存在的临时 `--legacy-profile` 路径。
后者防止 `init` 自动读取实际 legacy profile；只传 `--root` 并不能关闭默认 legacy 导入。
[root 与 legacy 路径](https://github.com/neonwatty/job-apply-plugin/blob/370204c58b1137d08c5a7e7449538ae6447be0b9/scripts/job-apply-store.py#L312)

合成 CLI 检查 **16 项通过**：隔离初始化、Unicode/标点规范化、同 scope 别名命中、不同 scope 不命中、inferred 仍返回、敏感保存无标记拒绝、有标记可查、同意时间生成、同 key 更新无 revision、更新后 session 引用不变、session 自定义 revision 被拒、不存在 key 可保存、missing/null 撤回、撤回后 session 仍 active、无 answer-delete、POSIX 私有权限。

另做一次并发观察：8 个调用线程启动 **24 次 helper CLI 写入全部成功**，最终只查到 **21 条记录，丢失 3 条**。这证明本次条件下发生 lost update；不是吞吐性能测试，也不是宣称每次都会丢相同数量。源码没有普通存储锁，与此结果一致。

另一个独立合成 scope probe 通过：显式 key 与 scope 不一致的写入被接受，`answer-find` 的 key fallback 返回了 scope 不匹配的记录。该结果证明 caller 的 scope 复核不可省略。

研究证据：

- 合成检查脚本：`/private/tmp/tomorrowstar-answer-library-check-20261009.py`；SHA-256 `31ffc03d756585ac3404bfd1e99395991630b1d719aff14170efd86887f1a890`。
- 脱敏检查结果：`/private/tmp/tomorrowstar-answer-library-synthetic-pzh8z65y/redacted-checks.json`，包含检查名、计数、源文件 hashes，不含答案值。
- scope probe：`/private/tmp/tomorrowstar-answer-scope-probe-9tgrsz0k/redacted-check.json`，只保留行为布尔值。
- 临时证据路径不承诺永久保留；本报告记录结论、基线和实际计数。报告本身保留在研究分支。
- 未读取或初始化默认申请者存储。未修改安装插件、clone、个人记录、职业图谱或其他研究票。

## 研究保留与 context pointer

研究分支：`D_m/research/application-answer-library`。
分支基线：`e4a26d0c24311d014d478f7f92e58a88e6709b4b`。
worktree：`/private/tmp/tomorrowstar-answer-library-research-20261009`，未初始化 submodules。
只提交本研究报告；当前主 checkout 的未提交实现不被复制或宣称已在基线 commit 中。
研究 commit 由子票的 resolution comment 指向；任务上下文为该票及其父地图。
