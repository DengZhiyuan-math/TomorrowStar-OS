# 确定页面需求识别与申请就绪规则

Type: grilling
Label: wayfinder:grilling
Status: closed
Priority: P1
Interaction: HITL
Assignee: Codex /root
Created: 2026-10-25
Parent: [简历与 Cover Letter 同岗并发生成接入规划](../map.md)
Blocked by: [确定两份材料的终审与独立采用](03-review-adoption.md)、[确定文本与 LaTeX 文件的交付契约](05-text-latex-delivery.md)
Triage: resolved

## Question

如何独立识别求职信材料及其文本／文件交付要求，在不漏掉可选入口的同时，
准确判断当前岗位是否已到提交前就绪？

需要明确：

- `cover_letter` 材料与 `motivation_text` 问答如何分别识别；同一 Cover Letter 的
  Attach／Enter manually 入口如何识别为交付方式，而非两封不同信件。
- required、optional、无交付需求、尚未核实的证据与优先关系；JD 明确要求和
  实际页面字段冲突、材料只在后续表单步骤出现时如何处理。
- 有入口默认交付（含可选），优先文本；页面明确要求两者时交付同一版本。
  生成侧和上传侧的可选 file 跳过条件都要纳入，不只改其中一处。
- 已知可选生成失败不阻塞已完成简历，必需材料缺失阻止最终就绪；但未知调用或
  写入／上传 intent、重要事实冲突、人工接管仍按原停止规则处理。
- 文本填入、文件上传、解析稳定及实际回读如何各自核验；复用正文不继承旧页回执。
  现有支持不足的 ATS 如何给出明确状态，不能以简历成功推定附稿成功。
- 前端只展示后端派生的两个材料状态、交付要求与失败原因，不维护第二套就绪算法。
  简历提前可用、求职信迟到时，材料交付如何继续而不覆盖页面人工值。

完成时记录分类规则、页面方式映射、就绪／等待矩阵、显示字段和各 Adapter 的范围。
不启动浏览器，不填写或上传，不改变最终 Submit 手动。

## Source locators

- [application_materials.py](../../../src/career_evidence_graph/application_materials.py)：material_kind／SupplementalMaterials._prepare_fields。
- [application_worker.py](../../../src/career_evidence_graph/application_worker.py)：field_material／_check_review。
- [application_worker_browser.py](../../../src/career_evidence_graph/application_worker_browser.py)：upload_supplement／process。
- [application_pipeline.py](../../../src/career_evidence_graph/application_pipeline.py)：单岗推进与等待。

## Comments

尚未领取或解决。本轮只建图；新决定记录为 resolution，不能把问题中的候选行为当作已实现。

### Resolution — 2026-10-25 源码实施

`cover_letter` 不随 file/textarea 改变身份，与 why/motivation 问答分开。
同一信件优先可用文本入口；页面明确两者必需才交付同一内容的文本和 PDF。
生成与上传两侧均移除可选求职信附件的静默跳过；其他材料保留既有边界。
后端派生 required/optional/none/unverified 和选定方式，JD 明确指令独立保留；
未观察字段或 JD 没提到不等于确定无要求。后续页面可重新观察和绑定。
必需未完成等待；可选已知失败明确显示而不阻塞已完成简历；未知/冲突/人工接管仍停止。
可选正文迟到时，只有仍持有当前页控制权才继续交付；用户接管后保持原 Continue 规则。
填写、附件、网站稳定和 readback 各自核验，未支持 ATS 不继承简历成功作为附稿成功。
前端展示后端状态和原因，不另算 ready；最终 Submit 手动。
见 [实施记录](../implementation.md)。
