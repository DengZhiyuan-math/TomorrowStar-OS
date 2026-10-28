# 材料准备候选：冻结与组合验证

对应[冻结候选版本并验证整条准备链](../gmail-resume-preparation-2026-10-17/issues/13-offline-batch-regression.md)，政策为 `preparation-policy/v1.0`。最终结果以 [verification.json](verification.json) 为准。

## 候选交接

[最终候选 manifest](candidate-v2/manifest.json)保存公共代码、静态界面、锁及配置、启动／构建源码、核心说明、许可证和选定合成测试的准确字节。它直接包含当前工作树中的未跟踪源码，不依赖提交状态。创建拒绝已有目标；只读 verify 检查精确文件清单、内容、配置及可选的当前源码一致性。

该快照是源码交接输入，完整离线套件在对应 checkout 运行，并在开始和结束核对候选／源码一致。它不包含完整历史测试资料，也不是安装包。后继安装票须继续核对构建 manifest、实际运行版本与窗口行为；本票没有构建、安装或启动 App。

[安装票交接记录](handoff.json)持有候选身份、准确路径、配置与后继核验要求，不授权提前执行安装或真实试用。

[早期候选](candidate/manifest.json)及[后继说明](candidate-supersession.json)保留。早期候选形成后补充了资料漂移场景的两个准确批次处置断言，最终检查使用后继候选，未覆盖旧包。

## 组合路径

1. 两页合成 Gmail、跨页来源去重与完整候选保留 → 缺 JD、German A2 对 B2 必需条件的资格冲突、已知模型失败分别停止 → 明确取得缺失 JD、手动重试并恢复 → 审阅草稿及具体 PDF → 停在 `waiting_application_record`。其他候选和未完成原因继续可见，不重读 Gmail。
2. 生成中贡献资料漂移 → 当前阶段以 `resume_inputs_stale` 失败并进入待处理，解释显示输入已过期 → 新草稿不被采用、旧草稿字节仍可读 → 取消其余未开始岗位、重开同一目录，零隐式重跑。
3. 已知 PDF 失败只隔离本岗 → 下一岗导出已保存但结果未知，全批停止 → 明确只读核验原回执，不重复生成或导出 → 复核该 PDF 后暂停，第三岗仍未开始。

这些测试复用真实 intake、匹配、草稿／PDF 存储与工作流，只替换外部 Gmail、取源、模型和流程用 PDF 传输边界。三个组合场景均保存原结果、审阅及失败状态，所有申请状态仍为 drafting，填写 worker 不存在。未调用邮件修改、ATS 或 Skill 评估。

## 证据

- [最终检查](verification.json)、[冻结前校验](candidate-verify-before.log)、[冻结后校验](candidate-verify-after.log)。
- [本票源码范围](source-manifest.json)、[有界差异](owned-changes.diff)、[源码回读](source-readback.json)、[既有文件保护](preserved-baseline.json)。本票没有修改运行时工作台或既有测试。
- [独立审查](review.json)：冻结器顶层路径穿越已修复；manifest 类型、精确清单、源漂移和只读行为有回归。最终无未解决阻断。
- [真实 renderer 运行](renderer-run.json)、[代码与配置绑定](renderer-binding.json)、[两页 A4 质量](pdf-quality.json)、[逐页图像一](page-1.png)、[逐页图像二](page-2.png)。从确切保存的四条合成选材导出；全文、文字／像素边界和逐页视觉检查通过。复制 PDF 的组合夹具只证明传输与工作流。
- [渲染 harness 来源](renderer-harness.json)及[运行时原字节核对](renderer-source-readback.json)：沿用原 renderer 专项，只更换新输出路径并拒绝覆盖。旧 PDF 和原验证证据保留。
- [票据回读](tracker-readback.json)、[文档链接](document-links.json)。

原始 RED、失败和成功日志均保留。组合测试初次失败分别是误读 explanation 字段和误把真实 store 漂移状态预期为 stale；实际契约为 failed 加 `resume_inputs_stale`，不是产品缺陷。冻结器的路径穿越和 manifest 类型测试是真实 RED→GREEN。验证过程中不将旧失败改写为通过。

## 边界

源码、合成组合、完整默认离线、浏览器兼容与实际本机 renderer 专项。没有读取私人资料或真实邮箱、修改邮箱、调用真实模型／岗位／ATS、写入用户 Skill 评估、上传或 Submit、恢复旧申请、启动／替换安装版 App、提交 Git 或写远端。准备路径没有 Skill 评估动作，完整离线领域测试仅使用临时合成数据。真实申请继续暂停。安装版、真实样本和真实简历人审仍待后继验收。
