# 28号票：复用同一主App安装证据结案

2026-10-21，Europe/Zurich。用户明确要求将只读结论同步给唯一维护操作者，待同一主App更新及隔离验收后继续28号票，不重跑旧证明矩阵。结论已同步，维护操作者已交付现成证据。本次只消费记录和更新文档，没有启动App、浏览器、worker、模型或测试，没有修改产品源码及正式运行数据。

**结论：28号票按票首2026-10-20当前精简范围完成。** 该范围已明确替代下方冲突旧验收；下表对应其7项。原负责人、依赖、历史正文及历史验收勾选保留。30/34和真实申请不因本票结案而完成或恢复。

## 当前7项与复用证据

| 当前验收 | 源码行为证据 | 本次安装支持与准确限度 |
| --- | --- | --- |
| 1 退役逐操作包、版本、nonce、epoch、短lease及原页proof门槛 | [运行连续性及后继准入迁移](../automatic-mainline-2026-10-21/runtime-assets/README.md)：诊断不再审批普通业务，健康会话和真实Continue保留 | G2/G3实际运行，G0实际权限有效；唯一App、固定签名和回滚均保留 |
| 2 只核对相关权限、事实与当前文件 | [普通操作切片](../ticket28-runtime-simplification-2026-10-21/operation-scope/README.md)：普通动作不枚举当前全库，仍核对联系方式、JD、资格；上传继续核对career/PDF/lineage | G3字段与附件使用现有接口。Flow Continue及材料采用仍可全事实检查，不声称所有路径零扫描 |
| 3 目标、owner、锁、暂停、intent/attempt及未知不重放 | [独立最终源码审查](../ticket28-runtime-simplification-2026-10-21/boundary-audit/final-review.md)：最后dispatch持锁复验；intent后contact/owner/PDF变动均在发送前停止，保留原intent | 四正式根完整inventory不变；旧owner、未知fill intent、附件和profile保全，不清除、不重放 |
| 4 原子检查点失败停止，measurement失败只诊断 | [运行连续性](../automatic-mainline-2026-10-21/runtime-assets/README.md)：telemetry/checkpoint RED与GREEN、STOP下resume拒绝且旧字节保留 | 同批实现随v3安装；未重新在安装版注入所有存储故障，复用已冻结行为回归 |
| 5 模型和未选目录局部降级，准确报告能力原因 | [启动切片](../ticket28-runtime-simplification-2026-10-21/startup/README.md)：missing/long/unknown-home真实loopback资料读写与模型局部失败、不回退CLI、未选preparation_root不挡启动 | G0主宿主两权限与责任链有效；历史准确缺权拒绝保留，本次未重新撤权 |
| 6 历史PID/目录不冒充活性，实际同岗占用与原页保护 | [普通操作切片](../ticket28-runtime-simplification-2026-10-21/operation-scope/README.md)、已有single-binding/admission行为回归：旧目标限定与真实claim/未决page/intent保护 | G3同根重开保留runtime/PID/page/document/字段/附件/PDF和空intent；真实历史根只作保全，不声称历史页仍活着 |
| 7 用连续性、局部失败和业务保护回归替代旧证明矩阵 | [28源码统一结果](../ticket28-runtime-simplification-2026-10-21/final-readback.json)和[最终安装v3结果](../main-app-maintenance-2026-10-21/final-readback.json)分别绑定各自冻结输入 | 原失败、回滚和诊断根因保持；没有重跑旧matrix或增加日常审批 |

独立只读审查也确认当前7项均有覆盖，没有发现当前范围内具体剩余缺口。其定位包括已有 `test_worker_runtime_continuity.py`、`test_application_single_binding.py`、`test_installed_write_admission.py` 及独立intent后dispatch守卫；本次未重跑这些测试。

## 安装候选与证据层次

- 最终v3候选为 `preparation-candidate-18bae4ebc37098b5a36727d99fa5986b059cd1c9197fd7547e5be3b04b2c66b5`，426候选文件、820冻结输入。完整默认4661通过、2跳过；浏览器86通过；受影响221通过。集合有重叠，不相加。早先28源码4552通过/2跳过、372浏览器属于自己的冻结基线。
- [维护记录](../main-app-maintenance-2026-10-21/README.md)及[逐项限度](../main-app-maintenance-2026-10-21/acceptance.md)记录首轮G1失败、实际回滚、后继修复和G0—G3。安装完整inventory匹配签名v3候选，四份旧包备份有效。
- [协调方独立只读回执](../ticket30-34-install-coordination-2026-10-21/installed-v3-independent-readback.json)核对95个engine和12个public输入、固定签名及820输入无漂移。controller/UI实际加载匹配manifest。
- worker实际 `loaded_engine_revision=null`，完整加载映射保持unknown；启动测量32文件匹配安装字节不代替完整callable加载证明。这是证据限度，不重新建立逐操作版本门槛。

## 保全与未声称的结果

正式四运行根完整inventory不变，正式配置最终与原始字节一致。工具曾读退出后的旧CUA句柄而误开普通窗口，随后正常退出；配置发生语义相同的JSON重排，原字节已恢复。事故与变后副本保持，不表述为维护全程从未读正式配置。

历史 `page_open=true` 不证明页面存活。未知结果、fill intent、旧owner、附件和profile保持。G3证明空intent的同页重开，不证明非空未知intent恢复；未新测活旧worker跨版本执行、真实人工值修改或自然人工Submit闭环。这些属于保留限度，不回填为已被替代的旧证明矩阵门槛。

30/34及其原验收、其他票的真实接受继续由原票持有。真实申请、填写、上传继续暂停，最终Submit人工。本次没有新增立即需要用户判断的问题。

原票、开发计划及地图改动前字节存于 `before/`；原tracker见 [tracker-before.json](tracker-before.json)。所消费证据摘要见 [evidence-inputs.json](evidence-inputs.json)，最后读回见 [verification.json](verification.json)。
