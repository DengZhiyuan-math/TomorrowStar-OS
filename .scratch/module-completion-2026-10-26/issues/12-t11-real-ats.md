# MC-12：T11.3 获授权真实 ATS 新接管链验收

Type: verification
Label: wayfinder:task
Status: open
Priority: P2
Interaction: HITL
Assignee: none
Created: 2026-10-26
Parent: [Module 剩余开发地图](../map.md)
Blocked by: [MC-11](11-t11-signed-gui.md)
Triage: awaiting-authorized-layered-acceptance

## 问题与范围

在适用站点/运行授权内验收新接管链；不替代旧 34 号票的自然手动 Submit 后下一岗闭环，也不替代 Workable/Ashby 的平台专属缺口。

## 文件所有权与并行边界

使用唯一主 App 与私有真实验收记录；复用已有平台入口，仅修具体暴露问题。一个当前岗位、一个写者；不能与其他真实岗位/同原页执行并发。

共享文件按地图的冲突规则协调；领取后才能写入。不得覆盖其他工作的修改。
依赖边表示必要交付，不表示外部运行授权；测试记录中的 deselected 不抵充覆盖。

## 验收条件

- [ ] 按当前验收规则选站点/岗位并在私有记录保存范围、URL、请求路径及结果，不向票复制个人材料。
- [ ] 新链实际填写、上传、回读、停止及原页保全分别有证据与限制；前两层通过不能推断本层成功。
- [ ] unknown/登录/验证码/未支持网络路径明确等待，无自动最终 Submit；不为凑验收强迫用户投递。
- [ ] 与既有平台票和真实闭环票逐项交叉引用，只关闭本票实际达到的适用范围。

## 既有证据与限制

[T11 第三层](../../../docs/module-interfaces-and-migration-design.md#t11-实际-codex签名-gui-与安装身份分层验收)。当前未操作真实申请，未获具体外部运行范围时本票保持 open。

需求以[正式设计](../../../docs/module-interfaces-and-migration-design.md)为准。R6 只证明原冻结源码与合成测试范围；本票如有新实现，
须记录实际改动、对应回归和审查，不能复用 R6 关闭新行为。未知结果、人工内容、原页、
原 journal 和历史记录保留，最终 Submit 手动。

关联历史范围：[原 Ashby 初始化票](../../single-job-application-flow-2026-10-16/issues/33-ashby-public-bootstrap-review.md)；其原状态、负责人和接受结论保留。
