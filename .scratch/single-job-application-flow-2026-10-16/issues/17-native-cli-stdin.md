# 修复原生父进程下 Codex CLI 的标准输入等待

Type: task
Label: wayfinder:task
Status: closed
Interaction: AFK
Assignee: 01a146b9/native_cli_fix
Created: 2026-10-17
Parent: [接通单岗位 JD 分析、专用简历与自动填写主流程](../map.md)
Blocked by: [将单岗位流程设为原生 App 默认运行方式](08-native-runtime.md)

## Question

安装版的只读 Gmail 调用等待超时，CLI 报告正在读取附加标准输入且没有事件。如何在保留原生后端父管道的同时，让独立 CLI 调用及时执行？

## Work and ownership

- 仅拥有 `src/career_evidence_graph/codex_cli.py` 与 `tests/test_codex_cli.py`；根执行者负责安装及票据。
- 先以未关闭的父输入管道和实际子进程建立秒级、离线、可重复 RED。依据观测区分标准输入等待、连接器与模型服务问题，不增大超时掩盖原因。
- 使用最小标准库修复；保留 prompt 参数、结构化输出、超时、私有捕获、工具只读及原生父 EOF 退出边界。
- 不改连接器权限、凭据、模型选择、评分公式、真实来源或既有运行。
- 不独占代码库，不回退他人修改。

## Acceptance criteria

- [x] 开放父管道下，独立 Codex CLI 不再等待父 EOF；有实际子进程 RED/GREEN 回归。
- [x] 原有 CLI 超时、错误、敏感输出及结构化输出回归通过。
- [x] 当前完整离线和包内运行时通过。安装版真实 Gmail 重验由第 14 票执行，不能由离线测试代替。

## Resolution comment

2026-10-17：安装版已在 App 点击只读 Gmail 刷新，随后超时并显示不可用。私人原诊断已保留；未导入/选择岗位或填写。尚未确定根因，先建立开放父输入管道的可重复回归。

开放父 stdin=PIPE、写入哨兵且保持写端的实际子进程回归两次 RED（约 1.7 秒），均报告读取附加输入、零 JSONL 和超时。仅为 exec 子 CLI 设置 stdin=DEVNULL 后 GREEN，原 prompt argv 核验通过，父进程仍完整读回监控哨兵；原生后端的父 EOF 机制未改。CLI/Gmail/匹配/简历组合 **195 passed、3 deselected**，两文件 Ruff/check/format 与 diff 检查通过。

冻结 `codex_cli.py` SHA256 `87ecf8ed2de445d0a00edb82cbb8499afc751318d9667d31119ab53aec031e6d`，专项 SHA256 `65c065765befb9a6b7003774d0b8679be6602734e520e7856cf7702ff83be9f7`。完整离线和新包正在验证，暂不关闭；真实 Gmail 仍由第 14 票承担。

2026-10-17 关闭：冻结源码完整离线 **1974 passed、151 deselected / 239.20s**，全仓 Ruff/check/format 通过。新包签名、搬移、内置运行时、离线 PDF 与父 EOF 退出验收通过，安装后真实原生 Gmail 搜索/读取已完成，原超时未再出现。见[新包验收](../assets/native-cli-fix-package-acceptance.json)、[源码/安装绑定](../assets/native-cli-fix-source-binding.json)和[实际 Gmail 入口验收](../assets/native-gmail-intake-acceptance.json)。修复仅隔离独立 CLI 标准输入；真实填写权限及最终岗位验收仍未完成。
