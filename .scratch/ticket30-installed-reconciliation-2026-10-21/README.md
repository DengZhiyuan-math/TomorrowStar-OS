# 30号票：安装证据复用与剩余核对

2026-10-21，Europe/Zurich。按用户要求复用同一主App更新和G0—G3隔离验收，逐项核对票首当前8项。**1—6项已有适用的分层证据，直接记录为满足；7—8项部分满足，共用一个实际worker加载映射缺口。** 本票继续claimed，原负责人 `01a15926/root` 和依赖不变。

本次只读现成记录、XML、冻结指纹、源文件和既有私人G2/G3原始回执，然后更新报告及票据。没有重跑测试或旧证明矩阵，没有启动App、浏览器、worker、权限探针、模型或维护，没有修改产品源码及正式申请数据。

## 当前8项逐项结果

| 项 | 记录结果 | 适用证据与覆盖层次 |
| --- | --- | --- |
| 1 邮件保存、标签归档、延后JD、分页去重与三路 | 满足 | G1实际保存标签、两页收录、归档丢回包后inspect且不重发；本次完整默认XML中20项matching_routes及邮件组合通过，涵盖低分、普通和精准路由。三路属于源码组合证据，没有宣称在G1逐路原生重演 |
| 2 指定岗、重要等待、一次继续、skip/return与重开 | 满足 | G1原失败根一次Continue、缺国家仍等待且只收录、skip/return保留原task/PDF；G3同runtime/page/document/字段/附件/PDF重开。人工编辑一次继续、健康恢复和显式等待由适用的既有公共行为回归补足，本次未在原生进程新注入人工值修改 |
| 3 普通动作、零自动最终动作、模拟人工结果续岗与未知不重放 | 满足，限已支持线路 | G3单次上传和远端SHA、更正邮箱不重传、自动Submit为0；历史22项接收端回归证明普通Next/草稿/上传、独立最终出口及人工原页Submit。当前完整默认包含真实Flow/Worker/Runner的success/rejected/unknown结果消费：只有success选择下一来源，其他结果留原岗；不声称第二worker已完成填传 |
| 4 能力、计量、落盘故障及按影响复用 | 满足 | G0实际宿主权限有效，G1/G3健康业务及材料保留；当前默认XML包含measurement失败只诊断、checkpoint失败保留旧检查点、STOP不能被resume清除，以及相关事实/文件保护。没有在安装版重新注入整套旧故障 |
| 5 主控、副本和审批收敛 | 满足 | 39/40/41已按源码条件结案，实际删除/共享清单、Worker页状态派生、GET不双写和默认控件已随v3安装；本次不再把旧源码收尾列为待做 |
| 6 默认、受影响、安装和模拟结果分层 | 满足 | v3默认4661通过、2跳过；受影响221通过；浏览器86通过；包内验证和G0—G3实际安装分别留证。集合不相加，跳过不计通过；真实材料质量和真实完整提交闭环另属原票 |
| 7 运行前后输入指纹及workspace/candidate/package/worker核对 | 部分满足 | 820输入无漂移、426文件候选、安装完整inventory、95 engine/12 public和controller/UI映射已核对；运行worker完整加载映射缺失 |
| 8 复用单App身份和已验证兼容范围，明确实际worker加载版本 | 部分满足 | 固定签名、同一路径安装、四份旧包备份、实际回滚、正式根及配置保全、G3同runtime重开均有据；实际worker的 `loaded_engine_revision=null`，完整映射保持unknown |

1—6由源码、模拟和实际安装多层证据共同支持。G0—G3没有单独完整重演所有三路、编辑和模拟人工Submit子场景。当前AC6要求分别记录这些层次，并未要求在native重新演一遍全部子场景；此处不新增该门槛。

## 唯一待补的合成验收边界

**实际运行worker的完整加载角色映射及其覆盖范围。** 7、8两项指向同一证据缺口，不是两个新实现。

本次先读已有私人G2 readiness、G2/G3 run及G3重开前后原始回执，实际值仍为null，未找到等价完整映射。包manifest的预期worker revision已存在；32个启动文件匹配、controller/UI匹配或相同版本号，都不能替代实际运行worker的callable加载证据。元数据读回见 [worker-mapping-readback.json](worker-mapping-readback.json)。

后继只需定位这处采集缺口，并为同一主App的一个有界合成worker取得绑定实际PID/run的非null完整角色revision，核对安装manifest并注明该进程实际执行的范围。新回执必须绑定自己的run，不能回填或改写旧G2/G3的unknown。当前不要求重建另一App、整套重装/回滚、重做已经通过的字段/上传或旧证明矩阵。

## 保留限度，不扩成当前前置

- 本次更新前没有活旧worker；活旧版本跨版本执行未测的事实保留，不专门制造一个旧进程来凑组合。旧worker不冒称热加载新源码。
- G3仅验证空intent重开。正式旧owner、未知结果、fill intent、附件及profile保全，不清除、不重放；保全不等于历史原页仍活着或非空未知intent已恢复。
- 真实Gmail、真实材料质量、真实人工Submit后的自然闭环由原真实票持有，不列为30合成验收的缺口。真实申请、填写、上传继续暂停，最终Submit人工。
- 首轮G1失败/回滚、工具误开普通窗口与配置JSON重排、G3准备顺序错误均保留；正式四根inventory未变，正式配置最终恢复原字节。不把维护描述为全程未读正式配置。

## 复用来源与适用性

- [同一主App维护记录](../main-app-maintenance-2026-10-21/README.md)、[原安装逐项限度](../main-app-maintenance-2026-10-21/acceptance.md)、[最终回执](../main-app-maintenance-2026-10-21/final-readback.json)、[独立安装核对](../ticket30-34-install-coordination-2026-10-21/installed-v3-independent-readback.json)。本报告是30的当前核对，不改写这些原始报告。
- [当前默认XML节点提取](reused-current-default-nodes.json)来自本次既有full-v3.xml，只读取结果，没有运行节点。候选为 `preparation-candidate-18bae4ebc37098b5a36727d99fa5986b059cd1c9197fd7547e5be3b04b2c66b5`。
- [历史Submit适用性](historical-submit-applicability.json)：旧28浏览器两份实际XML中的22个Submit接收端节点全部通过；测试模块、hosted_ats和Worker指纹与安装v3冻结相同。Runner整文件不同仅在CLI main的合成岗位URL委托，除main外整个模块AST相同。Pipeline/Flow的后继差异由当前默认组合覆盖。旧22项没有被写成本次v3的86浏览器重新执行；后者不含该模块，节点collection也没有被算作通过。
- [39状态收敛](../ticket39-41-source-2026-10-21/state-and-acceptance.md)、[40/41共享与保留调用](../ticket39-41-source-2026-10-21/materials-entrypoints.md)、[Flow结果组合来源](../ticket30-34-remaining-2026-10-21/README.md)。

独立只读审查确认上述1—6可按分层证据记录，7—8须保留partial。改动前票据/计划/地图字节在 `before/`，原tracker见 [tracker-before.json](tracker-before.json)，所消费证据摘要见 [evidence-inputs.json](evidence-inputs.json)，最终核对见 [verification.json](verification.json)。
