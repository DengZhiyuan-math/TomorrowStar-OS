# Cua 后台生命周期：最终修复与隔离复验

本轮完成已授权的本地修复及隔离合成复验。修复六个可复现缺陷，并复验此前的
无窗口 driver-owned 启动、scope 刷新、完整快照与未知结果不重发。
已安装应用、现有运行和原版版本准入保持。原票的安装验收仍开放。

## 可审阅交付

- [最终候选及源码绑定](candidate-final.json)：
  SHA-256 `1456e91897eceddba5d3747a24009d577d4b0129d4561df9482b4d66472ef9b5`。
  checkout 仅在显式设置 `TS_CUA_DRIVER_BINARY` 时允许该固定二进制。
- 上游 `trycua/cua`，base `c6cb386cf371fed3580ea1c5a238940ce4911641`，MIT。
  [完整补丁](upstream-full.patch)含之前生命周期修复；[后继补丁](upstream-successor.patch)
  相对前一封存候选源码。两者均作只读 reverse apply 检查，见[源码清单](source-changes.json)。
- [checkout 差异](checkout-change.patch)：固定候选 SHA、窗口发现期限、两项回归、文档及所属票记录。
  无新增依赖，Cargo.lock 保持。本地 Homebrew Rust/Cargo 1.98.1 debug 构建未安装、签发或发布。
- candidate-04 完成运行时修复；最终候选相对它只有 `cfg(test)` 的 FD 夹具变更。
  最终冻结后仅改开发测试 reaper 的复用，13 个运行时源码哈希和冻结二进制仍一致。

## 六项 red/green 与最小修复

| 缺陷及准确红测 | 修复及绿测 |
| --- | --- |
| Rust 就绪状态晚于原 3 秒期限仍被接受。`deadline-red.log` 的实际姿态循环返回 Ok。 | 成功条件也检查单调期限；`deadline-green.log` 通过。没有延长期限。 |
| worker 的 AppKit 查询暂时返回 nil，被 `try_wait` 当作进程已退出。真实 native lookup 故障令旧 candidate-03 报 DevTools 前退出。 | 活性读取内核 PID 启动时间；只有确认不存在或代次变化才算退出，读取失败传播。原生启动身份仍在主队列核验。candidate-04 [绿测](worker-identity-green-01-verification.json)通过；坏的 worker lookup 不再执行，故障 receipt 为 null。 |
| `wait()` 失败后 core 仍删自有 profile。文件回归四格中两格错误；真实终止拒绝时，旧候选删掉仍活着浏览器的合成待处理文件。 | 两个清理调用复用现有 stop/wait，确认退出才删；原生启动失败显式携带 `owned_process_exit_confirmed=false`。真实[绿测](cleanup-denied-green-01-verification.json)保留 sentinel 与 193 个 profile 文件。 |
| Python 窗口发现 2 秒到期后仍接受匹配标题；单次系统查询原可等 3 秒。 | 查询只用剩余预算，到期后不接受窗口，sleep 也受剩余预算限制。2.00/2.01 秒两项[红测](window-deadline-red.log)与[绿测](window-deadline-green.log)保留。 |
| macOS 端点发现测试的子进程继承了并发测试的第四个监听 FD；精确子进程注入稳定得到 expected 3 / actual 4。 | 只在测试 child 的 pre_exec 设置非白名单 FD 的 CLOEXEC，预分配枚举缓冲，溢出拒绝。精确绿测及默认并发 macOS 全集通过。生产发现逻辑未改。 |
| CLI 恢复集成测试仅杀 direct child，两个实际 daemon 仍在运行。精确重放 cargo 自身通过，外部[零遗留断言失败](recovery-teardown-red-verification.json)。 | 复用既有 testkit 的进程组 reaper；[两项复验](recovery-teardown-green-verification.json)通过，剩余新进程为空，未需外部清理。仅开发测试改动。 |

内核活性和 AppKit 身份分开核验。退出检查不会因 AppKit 注册/缓存暂不可读而误删 profile；
终止操作仍要求精确 AppKit launchDate，不因修复增加终止权限。无法确认退出时宁可保留诊断。

终止拒绝的 red/green 都是预期 `cua_refused`，不能把其 runtime 的 `passed=false` 改成启动通过。
独立、未注入的控制器随后按本轮 PID/launchDate 退出自有 Chrome；清理回执另存。
绿测 profile 归档为私有失败证据，原失败 runtime 的 closed=false 保留。

## 最终候选的真实 CuaDriver 对照

| 场景 | 结果 |
| --- | --- |
| 完整 worker 与强制 scope 更新 | [通过](final05-scope-result.json)。同一 transport/daemon、原 Page/同一 File 保留；旧绑定退休，越界来源拒绝。 |
| 完整快照与无关目录慢读取输入 | [12 次通过](final05-slow-catalog-result.json)，约 72–189 ms。修复后不访问该无关目录，延迟门没有执行。不是等待 16 秒后仍在 15 秒内返回。 |
| 完成点击后丢弃回执 | [通过](final05-unknown-result.json)。实际选择 1 次；2 个原生点击分别为展开和选择。原 15 秒期限，未知 intent 保留，后续 5 tick 和强制刷新无新派发。 |
| 主队列一次 native lookup 不可读 | [通过](final05-registration-01-verification.json)，prepare 1 次，约 0.940 秒。仍绑定原 PID/launchDate。 |
| 主队列持续不可读 | [预期拒绝通过](final05-deadline-01-verification.json)，prepare 1 次；姿态窗口仍 3 秒，整体 prepare 3.599 秒含启动和清理。 |
| 精确自有进程真实 SIGTERM | [预期拒绝通过](startup-exit-final05-verification.json)。一次 prepare；清理前 kernel_alive/profile_matches=false，没有重新启动。 |

每次只运行一个新建的自有系统 Chrome。Space 固定为 1，所有本轮原生样本均未观察到激活或上屏。
采样存在间隙，不作逐帧零闪现或统计可靠性声明。[完整逐轮结果](verification.json)保留候选和期望差异。
页面、PDF、来源均为隔离合成输入；真实 ATS、模型调用、网络上传、最终 Submit 均为 0。

## 回归结果

| 范围 | 最终结果 |
| --- | --- |
| Python 完整离线 | [947 passed，119 deselected](offline-final.log)。沿用仓库默认 marker，不传 `-m`。执行时候选为 04；随后仅换固定 SHA，并完成下列最终回归及真实候选对照。 |
| Python 最终受影响 | [30 passed，12 deselected](checkout-final05.log)，包括两项新的期限回归。 |
| Rust core | 986 passed，1 ignored。 |
| Rust macOS 库 | 570 passed，6 ignored，默认并发。 |
| CLI/MCP 单元 | 327 passed；helper 子进程的 10 个通过不重复计数。 |
| CLI 集成 | 83 passed，20 ignored。该次运行发现上述两个测试遗留，保留原结果；修复后精确恢复集成 2 项通过且零遗留。 |
| testkit | 112 passed，1 ignored。 |
| Ruff | [lint](ruff-final-02.log)通过，[格式](format-final-02.log)168 文件通过。封存 `.scratch` 排除，禁用缓存。 |

Rust 的原始构建、红测、绿测和上述完整日志在本轮 0700 持久私有目录，由[私有原件绑定](private-raw-binding.json)记录。
桌面交互的 ignored 测试保持跳过。没有借测试结果扩大真实桌面或 ATS 的支持声明。

## 事故、保全与未验收边界

- 所有红测、中间候选、首次 lint/format 失败、测试 daemon 遗留和精确清理回执保留。
  后继成功不覆盖原失败。测试遗留只按本轮专用可执行文件及内核启动代次处理。
- 用户提供的 PID 81448 / incident `4E82643A-B27A-426F-AE2D-F40EF9CF20B1`
  已与前轮沙箱内 Chrome for Testing 启动失败精确匹配；[原对应记录](../cua-startup-snapshot-rootcause-2026-10-16/user-crash-81448-correlation.json)保持封存。
  原因是显式 `-m not browser` 覆盖默认排除。正确离线命令已经固定，本轮未重现该误选路径。
- [保全回读](preservation.json)验证现有进程身份及私有记录/附件/设置、4077 个历史文件、
  前轮私有原件、1419 个安装应用文件、Cua 与 rollback 字节保持。新自有进程和 socket 均退出；
  活跃 profile 目录无残留，失败归档独立保留。
- [逐项完成审计](completion-audit.md)区分已完成本地修复、安装验收和历史归因。
  原 native-06/native-10 缺少对应阶段探针，仍不能唯一归因；Dock 重开事件上游的人类动作仍未知。
  跨 daemon、owner 到期后的保页及续权不增加保证。Guardian、TTL、来源上限、未知结果和发送守卫保持。
- 未更新已安装应用，未启用桌面代理，未推送或发布。原票的安装版完整后台验收保持开放。

原始诊断目录：`/Users/zhdeng/Library/Application Support/TomorrowStar/diagnostics/cua-final-repair-audit-20261016-01a1360f`。
公开后继只含合成结果和哈希；故障注入、采样器与修复脚本均留在本目录这一明确的诊断区域，不进入产品。
