# 独立申请 worker：平台可用性评估

> 历史评估：本文保留通用流程开发前的判断。2026-10-11 当前范围已增加通用原生控件与一个 ElevenLabs / Ashby 岗位的自动保存和附件挂接验证。当前流程及证据以[运行流程与测试总览](application-worker-workflow.md)为准。以下“当前”指评估当时，不限制后续已验证能力。

核验日期：2026-10-10。资料限于当前代码、已有验证报告和平台官方资料。本次没有登录、填写、上传或提交真实申请。

**当前可执行范围是 Lever / Greenhouse 的指定托管表单。企业自有招聘网页可以作为岗位发现入口，但不能直接交给现有 worker 填写。** 最小扩展是从企业页面找到同一岗位的已支持 ATS 直达链接，继续复用现有 worker。其他平台需要独立适配和验收。

## 当前证据与限制

| 证据 | 已证明 | 未证明 |
| --- | --- | --- |
| 既有离线回归：687 项通过 | 队列、答案范围、逐岗位 PDF、版本检查和人工交接契约 | 真实网站填表成功率 |
| 既有本地浏览器回归：20 项通过 | 合成 Lever / Greenhouse 控件、附件限制、暂停恢复和交接 | 其他企业的表单变体 |
| 真实 Lever / Greenhouse 各一页只读核验 | 对应页面的身份、标签和控件符合适配器预期 | 真实个人信息填写、附件上传、最终提交或招聘方接收 |

以上是[已有验证报告](../validation/application-automation/2026-10-10/live-worker-pilot/README.md)的证据。本次筛选改动的回归另见[筛选验证](../validation/application-automation/2026-10-10/job-screening/README.md)，不改写历史结果。

执行入口只接受 `jobs.lever.co`、`jobs.eu.lever.co`、`boards.greenhouse.io`、`job-boards.greenhouse.io` 上符合固定路径的 HTTPS 岗位。读取器只读取顶层 `form#application-form` 或 `form#application_form`，核验岗位 URL 和公司／岗位标题。它支持文本、原生 select、单选 checkbox/radio 和唯一标签的 ARIA combobox。iframe、任意表单、多选、额外必填附件和多步骤流程没有通用实现。[入口代码](../src/career_evidence_graph/application_automation.py)、[托管适配器](../src/career_evidence_graph/hosted_ats.py)。

人工接管前，网络 guard 只放行限定读取和内容哈希匹配的 Lever `/parseResume` 上传。当前核验的 Greenhouse 非 S3 表单把附件留在本地；S3 预上传会暂停。未知问题只暂停该岗位。登录、验证码和未支持控件需人工处理；接管后该页退出自动处理。最终 Submit 始终由用户操作。[执行代码](../src/career_evidence_graph/application_worker_browser.py)、[操作说明](live-application-worker.md)。

这套架构不依赖 Codex 内置浏览器。更换浏览器或增加模型不能替代平台身份、控件、步骤和资料发送路径的验收。当前同义复用使用固定已确认别名，没有启用模型匹配。[操作说明](live-application-worker.md)。

## 平台比较

“增量”是相对现有 worker 的工程判断，不是平台承诺或工期估计。除直接 Lever / Greenhouse 外，下表均为待开发。

| 平台／站点形式 | 当前可用性 | 最小扩展与主要障碍 | 官方依据 |
| --- | --- | --- | --- |
| 直接 Lever / Greenhouse | 已接入，真实填写待验收 | 优先用少量明确岗位验证已接入路径；继续保留 Submit 人工操作 | [已有验证](../validation/application-automation/2026-10-10/live-worker-pilot/README.md) |
| 企业域名，申请链接指向 Lever | 企业页本身不执行；保存核验后的托管直达链接可走现有入口 | 低增量：发现公开 `hostedUrl`／`applyUrl`，核对公司、岗位和 ID。Lever 官方不提供申请表 iframe，建议用托管申请页 | [Lever Postings API](https://github.com/lever/postings-api) |
| 企业域名，嵌入或定制 Greenhouse | 顶层页面与 iframe 不执行 | 低至中增量：识别 board token／岗位 ID，找同一岗位托管页；托管页不可用时进入人工流程。不能仅凭 `gh_jid` 或品牌标识放宽域名 | [官方嵌入说明](https://support.greenhouse.io/hc/en-us/articles/46365908766875-Embed-a-Greenhouse-job-board-on-your-career-site)、[Job Board API](https://docs.greenhouse.io/job-board.html) |
| Ashby | 不支持执行；公开岗位可用于发现和筛选 | 中增量，优先新增：公开 API 提供完整 JD、地点、工作形式和 `applyUrl`。新增托管表单、动态选项和附件发送适配。官方自建表单方案含签名文件预上传，不能假定选文件仍留在本地 | [公开岗位 API](https://developers.ashbyhq.com/docs/public-job-posting-api)、[自建招聘页与附件流程](https://developers.ashbyhq.com/docs/creating-a-custom-careers-page) |
| SmartRecruiters | 不支持执行；公开 Posting API 可用于发现 | 中至高增量：核验候选人页面、筛选问题、隐私选项和附件请求；先做只读预检。企业 Application API 受认证保护，不能作为个人求职者的提交捷径 | [Posting 端点](https://developers.smartrecruiters.com/docs/endpoints)、[Application API](https://developers.smartrecruiters.com/docs/application-api)、[认证说明](https://developers.smartrecruiters.com/docs/authentication) |
| Workday | 不支持 | 高增量：申请模板可改变教育、工作经历、语言等区块；Candidate Home 是否必需可由企业设置。需要逐步骤身份、重复履历、会话和发送检查；先限定一家企业的一个模板 | [申请模板](https://doc.workday.com/admin-guide/en-us/human-capital-management/recruiting/job-applications/ijz1499291475964.html)、[候选人账户与申请](https://doc.workday.com/workday-education/en-us/course-manuals/recruiting-for-administrators/prospects-and-candidates.html) |
| SAP SuccessFactors | 不支持 | 高增量：普通申请、Quick Apply 与新版候选人体验不同；账户、OTP、数据隐私和 picklist 需按企业配置处理。Quick Apply 名称不代表兼容现有单页适配器 | [Quick Apply 限制](https://help.sap.com/docs/successfactors-recruiting/setting-up-and-maintaining-sap-successfactors-recruiting/important-notes-related-to-quick-apply)、[新版候选人体验](https://help.sap.com/docs/successfactors-recruiting/setting-up-and-maintaining-sap-successfactors-recruiting/reimagined-candidate-experience) |
| iCIMS | 不支持 | 高增量：企业可配置不同步骤；账户、Submit Profile、Update Profile 与最终申请提交有不同含义。中间按钮可能写入服务器，不能按名称一律允许。支持 Finish Later 的网站也需实际恢复测试 | [官方候选人指南](https://community.icims.com/articles/Knowledge/Candidate-Guide-to-the-iCIMS-Talent-Platform) |
| Oracle Taleo Enterprise | 不支持 | 高增量：企业用多页、标准／自定义区块配置 application flow，还存在不针对岗位的 Candidate Profile 流程。需区分资料保存、页面推进、签名和最后投递 | [Application Flow](https://docs.oracle.com/en/cloud/saas/taleo-enterprise/20d/otcug/application-flow.html)、[Career Section](https://docs.oracle.com/en/cloud/saas/taleo-enterprise/20d/otcug/getting-started.html) |
| 企业完全自建表单 | 不支持通用执行 | 简单表单可逐站点适配，复杂站点按租户处理。先核验来源、全部控件、上传／自动保存和最终按钮请求；不能只放开域名或套用任意 input 填写 | 当前[身份与网络限制](../src/career_evidence_graph/hosted_ats.py)决定该结论；没有统一厂商契约 |
| LinkedIn Easy Apply | 不支持；暂不列为优先适配 | 已登录账户、多页弹窗、Review／Submit 和平台限制均需单独处理。优先走企业官网申请链接；官方 Easy Apply 集成面向招聘方读取申请，不是个人申请提交 API | [官方申请步骤](https://www.linkedin.com/help/linkedin/answer/a512388/apply-for-jobs-on-linkedin?lang=en)、[招聘方集成](https://learn.microsoft.com/en-gb/linkedin/talent/easy-apply)、[官方使用限制](https://www.linkedin.com/legal/user-agreement)、[Easy Apply 限额说明](https://www.linkedin.com/help/lms/answer/a512348) |

## API 与资料发送边界

公开岗位 API 适合读取 JD、地点、岗位 ID 和申请链接。**能读取岗位不代表拥有企业申请写入权限。** Lever 申请 POST 需要企业管理员生成的 key；Greenhouse 提交需要 Job Board API key；Ashby `applicationForm.submit` 需要认证与 `candidatesWrite`；SmartRecruiters Application API 需要客户／合作伙伴权限。[Lever](https://github.com/lever/postings-api)、[Greenhouse](https://docs.greenhouse.io/job-board.html)、[Ashby 认证](https://developers.ashbyhq.com/reference/authentication)、[Ashby 写入权限](https://developers.ashbyhq.com/reference/applicationformsubmit)、[SmartRecruiters](https://developers.smartrecruiters.com/docs/application-api)。

SAP `JobApplication` OData 属于有权限的招聘集成，字段操作受企业配置控制；iCIMS 客户接入属于正式集成项目；Taleo Web Services 用于企业信息集成。本次未证实 Workday 有供任意个人求职者调用的公共申请写入 API。不能将企业管理员权限视为候选人账户权限，也不需要索取雇主密钥来维持当前浏览器方案。[SAP JobApplication](https://help.sap.com/docs/successfactors-platform/sap-successfactors-api-reference-guide-odata-v2/jobapplication)、[iCIMS 客户接入](https://developer-community.icims.com/faq/how-can-i-get-access-specific-customer)、[Taleo Web Services](https://docs.oracle.com/en/cloud/saas/taleo-enterprise/otwsu/using-web-services.pdf)、[Workday SOAP API 范围](https://community-content.workday.com/en-us/public/products/platform-and-product-extensions/soap-api-reference.html)。

对新平台，附件上传、解析、自动保存、创建账户和中间“继续”都必须分别核验。停在 Submit 前不能自动证明个人资料未发送。未知请求、未知结果和挑战均暂停该岗位，不自动重传、不跨平台借用权限。这个规则应复用现有 guard 和人工交接契约。[执行代码](../src/career_evidence_graph/application_worker_browser.py)。

## 下一步优先级与验收

1. **先验证现有能力。** 每平台选 1–2 个符合已确认资格的真实岗位，逐岗位选 PDF。记录字段完成数、待补问题、附件是否实际发送、人工接管与页面保留。填写完成和招聘方接收分别记证据。最终 Submit 由用户操作。
2. **先扩展企业入口，再扩展平台。** 仅发现企业页公开的 Lever / Greenhouse 链接与嵌入标识；核验同一岗位后保留原来源，再交现有严格入口。没有确定映射时给人工链接。先不开发通用 iframe 填写或开放域名规则。
3. **下一平台选 Ashby。** 先接只读公开岗位资料和托管页预检，再实现一个已核验表单变体。复用队列、答案库、PDF 绑定和人工交接；只新增身份、控件和请求契约。官方资料支持它适合结构化发现，但其托管页面发送行为仍需只读与合成验证，不能由 API 文档推定。
4. **SmartRecruiters 次之；复杂企业 ATS 按需求接一家。** 仅在高价值目标岗位需要时，为 Workday／SuccessFactors／iCIMS／Taleo 选固定企业模板。保持人工账户／挑战处理。通用自建表单与 LinkedIn Easy Apply 暂缓。

新适配器进入真实批次前，必须完成：同一岗位识别、动态必填字段回读、上传内容与目的地约束、最终请求阻断、暂停恢复、不确定结果停机、人工修改保留和原记录去重。先用合成数据验证，再做授权的少量真实填写。当前没有足够真实样本给出成功率或“长期无人值守可用”的结论。


## 本日后续：通用流程已实现

[通用填表与岗位简历草稿](generic-application-worker.md)新增跨平台原生控件预检。
以上平台逐项评估保留为当时证据。通用控件复用减少基础填表重复，
但多步、iframe、自定义必填项和预上传仍须实际核验，不能据此宣布整个平台受支持。
