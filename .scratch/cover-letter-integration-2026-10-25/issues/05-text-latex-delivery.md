# 确定文本与 LaTeX 文件的交付契约

Type: grilling
Label: wayfinder:grilling
Status: closed
Priority: P1
Interaction: HITL
Assignee: Codex /root
Created: 2026-10-25
Parent: [简历与 Cover Letter 同岗并发生成接入规划](../map.md)
Blocked by: [确定 Cover Letter 正文契约与材料身份](01-content-contract.md)
Triage: resolved

## Question

怎样从同一已采用正文交付纯文本与按需 LaTeX PDF，并让固定信头、称呼、落款和
正文编辑范围保持准确？

需要明确：

- 模型正文进入当前唯一模板 `BEGIN LETTER BODY`／`END LETTER BODY` 区间的规则，
  LaTeX 转义、段落、字符及固定区字节保留如何验证。
- 文本框输出如何加入固定称呼和落款、还原普通字符；不维护第二份文本模板或正文。
- 首次文件需求才构建 PDF，复用现有 Prism 编译和导出 Interface 的具体接入点。
  文件绑定正文版本、模板与实际构建结果；不新建编译服务。
- 一页目标与实际溢出如何处理，保持正常字号与完整正文；不自动裁切或静默缩字。
- 页面限制字符数、文件大小或只接受非 PDF 格式时，最小可支持路径是什么；
  当前明确不支持的格式／平台如何报告，避免把未知能力写成已实现。
- PDF 失败／未知时正文如何保留，如何仅恢复构建；固定个人模板如何从私有配置
  绑定，如何用合成模板验证而不随 App 打包私人联系信息。

完成时记录渲染与构建 Interface、支持范围、文本／PDF 一致性及错误恢复规则。
当前模板和历史合成预览仅作输入，不重新设计版式、不实际编译或导出文件。

## Source locators

- [application_materials.py](../../../src/career_evidence_graph/application_materials.py)：export_material_pdf。
- [application_prism.py](../../../src/career_evidence_graph/application_prism.py)：现有构建与导出。
- [application_resume_versions.py](../../../src/career_evidence_graph/application_resume_versions.py)：构建版本绑定。
- [application_material_edit.py](../../../src/career_evidence_graph/application_material_edit.py)：当前编辑后的立即导出。
- [现有单文件模板](../../../assets/templates/cover-letter/main.tex)：仅作为只读设计输入。

## Comments

尚未领取或解决。本轮只建图；新决定记录为 resolution，不能把问题中的候选行为当作已实现。

### Resolution — 2026-10-25 源码实施

`render_cover_letter` 仅替换唯一 BEGIN/END LETTER BODY 区间，转义普通字符，
固定区字节保留；纯文本从同一模板读取固定称呼与落款，不含 PDF 信头或 TeX 命令。
模板通过现有私有 portal 配置、CLI 或环境变量显式绑定；原生启动保存并传递该路径。
不将个人模板作为默认安装资源，不改当前个人模板。
首次实际文件入口才请求现有 Prism Interface；文件绑定正文、模板、源、构建与实际 PDF 字节。
正文不因构建失败丢失。一页溢出/超大小不裁切或缩字；非 PDF 限制明确未支持。
已知构建前能力失败可仅重试文件；未知调用停止，完整本地回执可只读接回，
不完整回执不能重编译冒充恢复。Prism 可另行通过已有 read_compiled 读取准确结果，不能重放 build。
见 [实施记录](../implementation.md)。
