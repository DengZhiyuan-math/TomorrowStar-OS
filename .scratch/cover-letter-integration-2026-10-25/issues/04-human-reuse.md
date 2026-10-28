# 确定人工修改与已有文稿的复用

Type: grilling
Label: wayfinder:grilling
Status: closed
Priority: P1
Interaction: HITL
Assignee: Codex /root
Created: 2026-10-25
Parent: [简历与 Cover Letter 同岗并发生成接入规划](../map.md)
Blocked by: [确定两份材料的终审与独立采用](03-review-adoption.md)
Triage: resolved

## Question

新申请级 Cover Letter 正文如何复用旧字段稿、独立文本、人工 LaTeX 修改或页面
已有内容，并保留各自历史与人工意图？

需要明确：

- 哪些绑定足以将旧 field-bound 材料作为同岗可复用候选；缺少来源或内容映射时
  如何保留原稿而不假定已成功迁移。
- 多份候选稿冲突时的选择依据，已有人工正文／附件和迟到编辑如何优先保留；
  页面的非空值不能被生成结果自动覆盖。
- 正文变更如何形成新版本，如何独立影响文本与 PDF；仅切换输出形式无需重新写作。
- 固定模板变更与正文变更的影响分别是什么；无关库、模型或诊断元数据变化不使
  两份已完成材料全部失效。
- 新页面字段身份变化时，如何复用正文、重新建立本页交付绑定而不复用旧回读成功。
- 用户在 LaTeX 正文区修改后，哪些修改可唯一接回内容；无法表达的修改如何保全。
  不开发通用逆向 TeX 解析，也不批量改写旧任务。

完成时记录复用优先规则、人工保护与冲突处理、精确更新范围、旧任务兼容方案。
不迁移私库，不改当前打开的个人模板。

## Source locators

- [application_material_edit.py](../../../src/career_evidence_graph/application_material_edit.py)：edit_material。
- [application_materials.py](../../../src/career_evidence_graph/application_materials.py)：SupplementalMaterials._save。
- [application_worker.py](../../../src/career_evidence_graph/application_worker.py)：field_material／verify_material。
- [application_resume_versions.py](../../../src/career_evidence_graph/application_resume_versions.py)：现有人工内容与版本接回。

## Comments

尚未领取或解决。本轮只建图；新决定记录为 resolution，不能把问题中的候选行为当作已实现。

### Resolution — 2026-10-25 源码实施

人工非空文本和已有附件优先保留。旧字段稿只在原岗位/原字段/来源绑定可核验时复用；
缺少申请级映射的多稿不自动迁移，不批量改写旧任务。
正文编辑通过原条件保存形成受保护后继版本，并回写 Flow 申请级正文；原稿和历史保留。
两份存储间保存中断可核验接回，不重新写作。新内容使相应文件/版本对检查失效；
切换文本/文件或无关诊断变化不重新生成正文。
`capture-material-tex` 在暂停的当前岗位接回唯一映射的正文修改，固定区不变；
完整源与 diff 先保留，不能映射的修改明确停止，不开发通用 TeX 逆向解析。
新页面重新建立字段绑定，不继承旧页 readback；迟到人工值不被自动覆盖。
见 [实施记录](../implementation.md)。
