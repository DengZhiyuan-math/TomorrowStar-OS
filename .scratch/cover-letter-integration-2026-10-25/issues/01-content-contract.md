# 确定 Cover Letter 正文契约与材料身份

Type: grilling
Label: wayfinder:grilling
Status: closed
Priority: P1
Interaction: HITL
Assignee: Codex /root
Created: 2026-10-25
Parent: [简历与 Cover Letter 同岗并发生成接入规划](../map.md)
Blocked by: none
Triage: resolved

## Question

如何把同一岗位下的 Cover Letter 定义为可独立保存、检查、复用的正文材料，并让
后续文本框和 PDF 消费同一内容版本？

已确定的写作与交付原则见[产品约定](../PRD.md)。本票不重新讨论是否需要求职信。
需要明确：

- 从 `fixed_writing_inputs` 和现有固定材料交付中取哪些字段；完整经历事实与上游
  匹配如何交付，避免从简历成稿补造细节或重新检索。
- 正文的最小结构、段落身份、事实／推断引用、岗位绑定、写作要求和内容版本。
  模型输出正文，固定信头、称呼与落款不进入可变写作范围。
- 申请级正文身份与页面 requirement／field 身份的关系；正文就绪与文件就绪如何区分。
- 复用既有段落、来源及版本能力的最小范围；哪些简历专用字段不能直接套给信件。
- 用一份最小输入／输出示意记录 Interface、职责所有者与拒绝条件。未知 schema 名称
  和目录归属在本票决定，不预先增加通用 Material 平台。

完成时在 resolution 记录契约决定、最小示例、直接调用者和后继实施范围。
只形成方案，不修改生产 schema 或保存真实个人正文。

## Source locators

- [application_flow.py](../../../src/career_evidence_graph/application_flow.py)：fixed_writing_inputs。
- [application_single_binding.py](../../../src/career_evidence_graph/application_single_binding.py)：read_delivered_material_inputs。
- [application_materials.py](../../../src/career_evidence_graph/application_materials.py)：generate_material／SupplementalMaterials._save。
- [application_resume_content.py](../../../src/career_evidence_graph/application_resume_content.py)：现有内容契约。

## Comments

尚未领取或解决。本轮只建图；新决定记录为 resolution，不能把问题中的候选行为当作已实现。

### Resolution — 2026-10-25 源码实施

本轮用户已授权直接实施 PRD，技术细节由现有代码决定；原规划限制由地图的实施授权取代。
`application_cover_letter.LetterContent` 保存 `cover-letter-content/v1`：岗位身份、
固定输入版本、语言、稳定段落 ID、正文、fact/motivation、来源 ID/原文引用、人工保护与内容 revision。
申请级正文独立于 field/requirement；模型不写信头、称呼或落款。
直接调用者是 Portal 的 Flow callback，输入来自 `fixed_writing_inputs`、已保存来源归档及
完整 material packet 的同一投影；不使用简历成稿扩写，不重读职业库。
例如一项 fact 段落为 `{id: technical-experience, kind: fact, text: <正文>,
source_ids: [<已交付来源 ID>], source_quotes: [<逐字引用>]}`；程序补入保护与版本字段。
身份不符、资料包校验失败、越界/失效引用、重复段落及原生回执绑定不符均拒绝采用。
正文 ready 不代表 PDF 或页面交付 ready。后继调度、检查、渲染消费同一内容版本。
源码和验证入口见 [实施记录](../implementation.md)。
