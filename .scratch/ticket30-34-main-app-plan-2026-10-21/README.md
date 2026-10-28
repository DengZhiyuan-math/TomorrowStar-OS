# 30/34：同一主 App 更新、回滚与最小安装验收方案

2026-10-21，Europe/Zurich。**准备完成，执行未获恢复。App 构建、更新、安装、启动和真实申请继续暂停。** 本轮只读源码、原安装包和历史收据；没有运行权限探针、包验证器、浏览器或模型，没有读取真实配置、任务、邮箱或 ATS。

## 当前结论

- [30](../single-job-application-flow-2026-10-16/issues/30-installed-minimal-regression.md)：claimed，01a15926/root，awaiting-app-update；[34](../single-job-application-flow-2026-10-16/issues/34-email-to-review-pipeline.md)：claimed，同一负责人，source-integration-followup。两票直接依赖09/38/42均closed。39/40/41已按源码条件closed，不再列为未实现。28仍open，安装与适用交接由原票持有；33仍claimed，真实Ashby接受未验。此次不改变任何票头、依赖、勾选或历史。
- 最新冻结来源是[39/40/41最终v2](../ticket39-41-source-2026-10-21/README.md)：`preparation-candidate-3f68396549b88e53900c2c1d074d3737e0369fa4ec57875f19c7aed194c1ceb9`，426文件；820项测试/依赖等登记输入本轮逐项读回0变化。候选是源码交接，**不是安装包或独立完整测试checkout**。
- 复用该轮原日志：默认离线4656通过、2跳过、572 deselected；受影响476通过、1 deselected；本地浏览器86通过。集合重叠不相加，本轮未重跑。两项skip不是通过。30/34早期4641等结果只绑定各自旧输入，不能替代最新记录。
- 唯一安装路径实际为`/Users/zhdeng/Applications/TomorrowStar.app`，bundle ID `dev.tomorrowstar.desktop`；本轮严格签名检查通过。旧包manifest的92项engine输入中，64项与当前相同、28项不同；当前另有3项新增engine源码。旧包12项native/public输入中2项不同。旧manifest与包内engine字节0差异，**不代表已装入新源码**。版本号仍0.1.0/1，不能用它证明相等。
- 进程枚举`/bin/ps`被当前沙箱拒绝，未升级权限或重试。当前App/worker活性、原页、在途动作和实际加载版本均未核验。没有把磁盘manifest的loaded_code当成运行worker读回。

逐项剩余见[验收矩阵](acceptance.md)，可审阅的维护和场景命令见[执行方案](runbook.md)。证据：[实时票据](tracker-selection.json)、[候选核验](candidate-verify.json)、[820输入读回](frozen-input-readback.json)、[安装包只读核对](installed-readonly.json)、[源码差异](installed-source-comparison.json)。

## 集中需要用户决定

| 决定 | 建议范围 | 当前状态 |
| --- | --- | --- |
| 1. 何时恢复同一主App更新与隔离安装验收 | 一次授权窗口包含固定身份检查、构建私人候选、包验证、备份、替换唯一主App、无提示权限诊断和下列G0—G3；普通检查/材料/Continue不逐次再请示。若新包或场景失败，在旧包可核验且相关进程已安全退出时允许按方案回滚包。 | **待决定，本轮不执行。** 推荐先仅恢复这一范围，真实申请保持暂停。 |
| 2. 若维护窗口发现仍有原页或在途worker，如何安排交接 | 默认保留原页、附件、人工编辑和未知intent，延后替换；由28/30原负责人核对实际owner和精确版本兼容，安全交接完成后再更新。不要强退或以新目录绕开未决原任务。 | 这是条件性选择；当前活性未知，不能预先判定必须关掉某页。没有在途任务时不需另问。 |
| 3. 何时另行恢复真实申请体验验收 | 与App更新分开。恢复时按用户愿意投递的不同真实岗位验证真实邮件/JD、材料质量、填传和自然人工Submit后结果/下一岗；不为测试强迫投递。 | **继续暂停。** 本次安装合成授权即使恢复，也不包含真实邮箱、ATS或真实提交。最终Submit始终人工。 |

无需用户决定源码模块取舍、逐组PDF批准、每次Continue、重复权限检查或重跑已经通过的整套回归。签名身份不轮换，不创建第二个App，不重置TCC。仅在实际操作所需能力缺失时请求对应的系统操作。

## 最小验收的出口

G0—G3可证明新包实际加载及固定合成子范围，不能据此关闭34的真实人工Submit闭环。30仅在其8项当前组合条件均有适用证据后结案；矩阵明确保留未由最小场景覆盖的项目。原28/33及真实材料、控件、附件接受不被代签。旧失败日志、旧候选和原安装备份全部保留。
