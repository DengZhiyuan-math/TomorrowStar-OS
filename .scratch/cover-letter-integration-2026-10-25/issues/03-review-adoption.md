# 确定两份材料的终审与独立采用

Type: grilling
Label: wayfinder:grilling
Status: closed
Priority: P1
Interaction: HITL
Assignee: Codex /root
Created: 2026-10-25
Parent: [简历与 Cover Letter 同岗并发生成接入规划](../map.md)
Blocked by: [确定同岗并发写作与局部恢复](02-concurrent-generation.md)
Triage: resolved

## Question

如何覆盖简历与 Cover Letter 新表达的终审，又不让非必需求职信阻塞已经完成的
必备简历，且两份材料始终各自绑定准确内容版本？

需要明确：

- 何时共享一次终审输入，何时单独检查后完成的材料；共享审查规则和增加重复
  模型审查的区别。保留现有已完成审查，不每次重审两份。
- 终审消费固定上游与本轮新表达，不重新解读 JD、匹配、评估事实可信度或研究能力。
- 两份新表达之间的事实一致性如何核对；只出现于一份的相关细节不自动算冲突。
- 一份通过、一份需局部改写或结果未知时如何分别采用；审查补丁只修改对应材料。
- 人工保护的内容、已有人工稿与模型新增内容分别如何进入检查；不能以模型终审
  重写固定信头和落款，不能把人工编辑后快速校对变成新内容改写。
- 简历先完成且页面不要求求职信的具体时间线；两路先后完成、局部返工和迟到
  审查响应的绑定与复用条件。

完成时记录审查拓扑、检查与采用 Interface、内容版本绑定和有代表性的时序表。
不新增逐稿人工批准，不执行真实终审。

## Source locators

- [application_experience_content.py](../../../src/career_evidence_graph/application_experience_content.py)：review。
- [application_resume_versions.py](../../../src/career_evidence_graph/application_resume_versions.py)：persist_content_generation。
- [application_materials.py](../../../src/career_evidence_graph/application_materials.py)：新表达检查与正文保存。
- [application_proofread.py](../../../src/career_evidence_graph/application_proofread.py)：人工返回快速校对。

## Comments

尚未领取或解决。本轮只建图；新决定记录为 resolution，不能把问题中的候选行为当作已实现。

### Resolution — 2026-10-25 源码实施

简历沿用既有单一语义终审；求职信检查其新表达，允许定位到未保护 AI 段落的文字补丁。
第二份终审可消费第一份的准确内容版本。若两份终审都未覆盖最终版本对，
`application_material_consistency` 只补一次事实矛盾核对；已有准确版本对终审则复用，
不重复完整审稿，不等待可选求职信才采用必需简历。
只出现于一份的相关细节不算矛盾。检查不重新解释 JD、匹配或评估来源可信度。
每份结果绑定输入/内容 revision、原生 prompt/schema 和原始回执；补丁不触碰固定区或人工保护。
独立成功可采用；已知局部表达失败保留原稿并局部改写；未知结果停止并只读恢复。
人工正文不冒用旧 AI grounding，一致性核对保留其人工来源。
排队后正文变化会更换尚未启动的版本对；已运行旧检查保留结果或未知状态，不能遗忘。
见 [实施记录](../implementation.md)。
