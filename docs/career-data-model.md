# 职业资料数据库设计 — 2026-10-30 草案

本文是申请侧职业资料存储的目标设计。它落实
[记录契约重构决定](career-experiences.md#记录契约重构决定--2026-10-30)
中用户确认的六项决定，并给出完整的实体、约束、派生视图和迁移方案。
研究侧的 Experience → Contribution → Evidence → Skill 模型保持不变，只对齐词汇。

存储仍使用私有工作区中带版本的 JSON 文件和不可变历史，不引入数据库引擎；
项目约定只有在出现并发写入或查询规模需求时才考虑 SQLite。

## 1. 现状问题（实测依据）

整库匹配输入共 245 KB，其中正文只有约 81 KB。问题如下：

| 问题 | 现状 |
| --- | --- |
| 学历多处存放 | 简历资料、保留简历分组、申请答案（学位、毕业时间）、运行时复制到信息库的一份、LaTeX 模板。另有四处各自写了排除学历的过滤 |
| 词汇不统一 | 「谁做的」有 4 套写法；「做到哪一步」有 5 套，其中一套靠正则从文字里推断 |
| 标记事后补上且互相矛盾 | `resume_eligible`、`match_eligible`、`rewrite_allowed`、`documentary_only`、`design_only`、`planned_only`、`application_trusted`、`review_status` 在多处计算，在已确认资料规则下又被统一覆盖 |
| 来回复制再去重 | 经历抬头先复制进每条事实，生成模型输入时再去重；结构化字段先拼成文字，再从模型输入里删掉 |
| 混排 | 305 条事实中，第三方背景 130 条与本人事实混在一起；`agent_assisted` 7 条同时包含「本人在 AI 协助下完成」和「AI 完成、本人没做」两种含义 |
| 审计说明与事实边界混写 | 范围说明 90 条中约 53 条是审计套话，与真实边界写在同一段文字 |
| 状态缺失 | 模型输入中约 47% 的条目状态为 unknown |

## 2. 设计原则

1. **每个事实只有一个权威来源。** 派生内容只能重建，不能编辑，也不能反过来成为事实。
2. **事实、出处、审计分开存放。** 事实内容只记录职业事实；出处指向不可变的原始资料；
   审计说明和整理过程单独保存。
3. **结构化字段优先，不再从文字推断。** 是否在做、是否计划、谁负责，都由字段表达。
4. **只有一套词汇。** 旧词汇只在迁移时映射一次。
5. **所有写入都带版本。** 写入时校验当前版本（CAS），保留不可变历史，不能静默覆盖。
6. **模型只读派生视图。** 程序核验永远读取存储记录，模型输出的短编号由程序换回原始 ID。

## 3. 两层结构

沿用原有的两层设计，并把两层的职责写清楚：

| 层 | 内容 | 用途 |
| --- | --- | --- |
| **第一层：信息库** | 基本信息：学历记录、申请答案。<br>经历目录：每段经历的标题、类别、时间、机构、技能检索词、工作摘要、工作方向名称和版本 | 基本信息每次匹配都完整发送，不经过筛选。目录只在需要先选经历时发送，也用于排序和展示 |
| **第二层：经历库** | 每段经历的全部细节：事实、背景资料、来源、边界 | 装得下时整库发送；装不下时只发送选中经历的完整内容 |

两层的关系：

- 目录由经历库派生，绑定经历内容版本，随经历一起更新。技能检索词和摘要只能来自已保存的事实，
  不代表熟练度，也不代表本人独立完成。
- 基本信息不属于目录筛选的对象。学历和申请答案每次都完整进入匹配，避免像本次实验那样，
  因为选资料步骤漏掉已获得的硕士学历，而把学历要求判成不满足。
- 现在的目录（`directory.json`）共约 105 KB，大部分是别名、材料分组、版本等记录字段；
  摘要和检索词是机械生成的。目标目录只保留匹配和选择需要的字段，预计约 25–30 KB。

匹配时两层的使用方式：

1. 基本信息每次完整发送。同一次调用里，目录和完整经历不会同时出现：目录内容由事实派生，
   整库发送时它是重复内容。
2. 第二层整库能放进匹配上限：直接整库发送，一次调用完成匹配。这是当前的默认情况，
   实测 31 秒。
3. 第二层放不下：先用一次调用根据第一层选出经历，再发送选中经历的完整内容。
   不再分批读取和摘录正文。

「先筛选经历、再算匹配和写简历」的顺序保留，区别只在由哪一步完成筛选：

- 整库发送时，匹配调用同时完成筛选：它对每条要求引用支撑的事实 ID，被引用的经历
  按要求权重排序，就是简历要写的经历。简历和求职信再读取这些经历的第二层事实写内容。
- 整库装不下时，仍由一次单独调用根据第一层先选经历。

两种方式由程序按体积选择。第一层目录整理好之后，用同一批 JD 实测两种方式的判断和
简历选材，再决定整库发送的上限。

## 4. 存储布局

沿用现有私有资料目录，只调整其中的集合：

```
tomorrowstar-career-data/
  library.json                      库清单：各集合当前版本与库版本
  # 第一层：信息库
  education/
    records.json                    学历记录集合（含版本）
    history/<revision>.json
  .tomorrowstar-experiences/
    directory.json                  经历目录（第一层，由经历库派生）
  # 第二层：经历库
  .tomorrowstar-experiences/        经历记录（沿用现有 ExperienceStore）
    <sha(experience_id)>/<revision>.json
  .career-evidence/raw/<sha256>     原始资料，只追加（沿用）
  views/
    <library_revision>/matching.json    匹配视图（派生）
    <library_revision>/handles.json     短编号到原始 ID 的对照（派生）
```

申请答案仍然是 `single-job-worker/answer-library/answers.json`，属于第一层基本信息，
只收窄内容，不搬位置。

### 库版本

`library.json` 记录 `education`、`experiences`、`sources` 三个集合的当前版本，以及由它们
计算出的 `library_revision`。申请信息库有自己的版本。岗位分析只绑定两个值：
`library_revision` 和 `information_revision`。现在分散的 `sources_revision`、各条来源摘要和
读取回执都不再作为绑定输入。

## 5. 实体

### 5.1 学历记录 `education-record/v1`（唯一学历来源）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | 字符串 | 稳定 ID |
| `level` | `bachelor` \| `master` \| `doctorate` \| `other` | 学位层级 |
| `degree` | 文本 | 学位原名，如 M.S. Fundamental Mathematics |
| `field` | 文本 | 专业 |
| `institution` | 文本 | 学校 |
| `location` | 文本，可空 | |
| `start`、`end` | `YYYY` 或 `YYYY-MM`，可空 | 实际起止时间 |
| `status` | `awarded` \| `in_progress` \| `discontinued` | 已获得、在读或中止。在读时 `end` 是预计完成时间 |
| `details` | 文本列表 | 论文方向、导师、奖学金、项目名等 |
| `source_refs` | 来源 ID 列表，至少 1 个 | |

派生内容（不再单独保存）：
- 申请答案中的「当前学位」「毕业时间」等由学历记录计算。
- 资格检查只读学历记录。不能把在读记录推断为已获得学位。
- 简历学历区块由学历记录生成。LaTeX 模板中的学历文字由程序逐项核对，不一致时提示，不自动改模板。

### 5.2 经历目录条目 `experience-directory/v2`（第一层）

每段经历一条，由经历内容派生并绑定其内容版本：

| 字段 | 说明 |
| --- | --- |
| `experience_id` | 指向第二层经历 |
| `title`、`organization`、`start`、`end` | 识别与展示 |
| `skills` | 技能与技术检索词，每个词指向支撑它的事实 ID；只在团队或背景资料中出现的技术要标明来源层次 |
| `summary` | 1–3 句工作内容与问题领域摘要 |
| `content_revision` | 绑定的经历内容版本 |

`skills` 和 `summary` 在经历保存时由模型依据事实生成，用户可以修改；修改记入历史。
内容版本变化后目录条目必须重新生成，否则目录视为过期。

### 5.3 经历 `experience-record/v3`，内容 `experience-facts/v2`（第二层）

字段只放所有经历共有的属性。只适用于部分经历的信息，例如参与方式、项目已放弃、
只是听众、具体时间不同或职责未记录，都写成这段经历的一条事实，不另设字段。

**经历：**

| 字段 | 说明 |
| --- | --- |
| `experience_id` | 稳定 ID，不可修改；与 `candidate_id` 合并为一个 ID |
| `title` | 经历名称 |
| `role` | 职位 |
| `organization` | 机构，可空 |
| `location` | 地点，可空 |
| `start`、`end` | `YYYY` 或 `YYYY-MM`；`end` 为空表示至今 |
| `sources` | `[{id, locator}]`，本段经历引用的原始资料。现有来源 ID 已全局唯一，沿用 |
| `facts` | 本人、团队、他人或编码代理所做的事 |
| `context` | 背景资料 |

**事实 `facts[]`：**

| 字段 | 说明 |
| --- | --- |
| `id` | 经历内唯一，历史引用不改 |
| `text` | 一句直接陈述的事实，不写整理过程 |
| `responsibility` | `user` \| `team` \| `other_person` \| `agent`。`agent` 表示编码代理完成、本人未做。迁移后旧值 `agent_assisted` 暂时保留，按经历清理时拆成 `agent` 或 `user`/`team` |
| `status` | `completed` \| `in_progress` \| `planned` \| `unknown` |
| `source_refs` | 本段经历 `sources` 中的 ID，至少 1 个 |

**背景资料 `context[]`：** `id`、`text`、`source_refs`。描述网站、仓库、他人说法等，
永远不计为本人工作。

**存档字段**由程序维护：`revision`、`previous_revision`、`saved_at`、`actor`、`origin`、
`event_id`、`input_revision`、`metadata`、`materials`、`migration`（导入覆盖记录）和 `notes`
（审计说明，见 5.5）。存档字段不属于事实内容，不影响内容版本，也不进入匹配视图。

**约束：**
- `facts` 和 `context` 的 ID 合在一起在本段经历内唯一。
- `source_refs` 必须在本段经历的 `sources` 中存在。

### 5.4 申请信息库 `answers.json`（收窄）

只保存不属于职业事实的申请答案：

- 联系方式与身份：不进入匹配；
- 工作许可、签证、到岗时间、实习时长、薪资：参与资格判断；
- 语言能力：自报等级按原级别使用；
- 数据保护同意：用户长期同意集团内转交、保存期限和隐私处理的问题，统一记为
  `data_processing_consent`；背景调查、营销和其他协议仍按各自问题处理；
- 偏好；
- 敏感人口信息：仅在明确需要时填写。

记录字段沿用现有 `key`、`value`、`state`、`scope`、`sensitivity`、`source`、时间戳。
删除与学历重复的答案；这些答案改为从学历记录计算。答案的出处只留在记录里，不进入匹配视图。

### 5.5 审计说明（经历记录的存档字段 `notes`）

审计说明随经历记录一起保存版本和历史，不另建存储：

| 字段 | 说明 |
| --- | --- |
| `fact_id` | 对应的事实或背景资料 ID |
| `text` | 原范围说明全文 |
| `status` | `pending`：尚未清理；`resolved`：真实边界已写成事实，审计部分保留在此 |
| `context_status` | 仅背景资料：迁移前的状态值，保证迁移不丢信息 |

`pending` 说明在清理前仍以旧形式提供给匹配，避免清理完成前丢失真实边界；
`resolved` 后不再进入匹配。AI 协助等内部来源信息在清理时记入对应事实的说明。

研究侧的 Grill-Me 审计仍使用自己的 `audit/` 模型；两边通过 `experience_id` 和事实 ID 关联。

## 6. 统一词汇与映射

| 旧值 | 新值 |
| --- | --- |
| 事实 `third_party` | 移入 `context` |
| 事实 `agent_assisted` | 清理时二选一：编码代理完成的记为 `agent`；本人或团队在协助下完成的记为 `user`/`team`，协助信息记入审计记录 |
| 事实 `user`、`team`、`other_person` | 不变 |
| 研究侧 `non_responsibility` | 对应 `context` 或 `other_person` |
| 研究侧 `delivered` / `partial` / `planned_only` / `unresolved` | `completed` / `in_progress` / `planned` / `unknown` |
| 正则推断的 `planned_only`、`design_only` | 删除；由 `status` 和事实原文表达 |
| Contribution 表格中的 Codex / Codex-assisted | `agent` / 本人负责并在审计记录中注明协助 |

## 7. 删除的标记及其替代规则

以下标记不再保存也不再计算，由结构化字段直接得出：

| 删除 | 替代规则 |
| --- | --- |
| `match_eligible`、`application_trusted`、`review_status`、`documentary_only` | 库中所有学历、事实、背景资料和非联系方式答案都参与匹配 |
| `resume_eligible`、`rewrite_allowed` | 简历可写：`responsibility` 为 `user` 或 `team`（保留团队措辞），且状态为 `completed` 或 `in_progress`；`planned` 只能写成计划；背景资料和 `agent` 不能写成本人工作 |
| `design_only`、`planned_only` | 由 `status` 和原文表达 |
| `attribution`、`boundaries` 文本 | 由 `responsibility`、`status` 和事实正文表达 |
| `context_range`、`original_text_chars`、读取回执 | 整库读取时不需要；仍需要分段读取时由程序内部保存，不进入视图 |

## 8. 匹配视图（派生）

在库版本变化时生成一次，匹配、简历写作和求职信共用同一份。视图分成两部分，
对应两层结构：`basics` 与 `directory` 来自第一层，`experiences` 来自第二层。
每次调用只带 `basics`，加上 `directory` 或 `experiences` 之一，不同时带两者。
下例是整库发送；选经历的调用把 `experiences` 换成 `directory`。

```json
{
  "library_revision": "…",
  "basics": {"answers": [["A4", "work_authorization", "…"]]},
  "education": [{"id": "D1", "level": "master", "degree": "…", "institution": "…", "status": "awarded", "end": "2022"}],
  "experiences": [{
    "id": "E1", "title": "…", "role": "…", "organization": "…", "start": "2025", "end": null,
    "facts": [["F12", "user", "completed", "Led team delivery of …"]],
    "context": [["C3", "Website describes FastAPI on AWS Lambda …"]]
  }]
}
```

- 短编号 `D`/`E`/`F`/`C`/`A` 只在本视图内有效。`handles.json` 保存短编号到原始 ID 的对照。
  模型输出先换回原始 ID，再由程序逐字核对引文。
- 不包含审计说明、AI 协助记录、来源定位、核验字段和联系方式。
- 提示词顺序为：固定指令 → 匹配视图 → 当前岗位（JD、JD 解读、要求列表）。
  同一库版本下处理多个岗位时，前面部分完全相同，可以利用模型服务的前缀缓存。
- 要求列表只引用分组编号，不再重复整段分组；JD 只出现一次。
- 整库发送：`basics` 加全部 `experiences`，预计约 100–120 KB（现在 245 KB）。
- 整库装不下：第一次调用带 `basics` 与 `directory`（约 30 KB），例如
  `{"id": "E1", "title": "…", "skills": ["FastAPI"], "summary": "…"}`，选出经历；
  第二次调用带 `basics` 与选中经历的 `experiences`。`basics` 很小，两次都发送。

## 9. 一致性与核验

| 核验 | 读取对象 |
| --- | --- |
| 引文逐字核对 | 存储中的事实、背景或学历原文 |
| 引用归属 | 简历只能引用 `user`/`team` 事实；背景资料只能作为说明 |
| 资格判断 | 学历记录、申请答案 |
| 版本绑定 | 分析绑定 `library_revision` 与 `information_revision`；任一变化都需要重新确认输入 |
| 写入 | 校验当前版本（CAS）、不可变历史、`experience_id` 不可改 |
| 原始资料 | 只追加；更正保留历史 |

## 10. 不变的部分

- 研究侧模型和 Grill-Me 审计流程；
- 原始资料存储；
- 岗位、申请任务、分析和投递记录（只把绑定字段换成库版本）；
- 申请信息库的位置和写入接口；
- 最终提交保持手动。

## 11. 迁移方案

每一步都可以单独验证、单独提交；旧版本记录保持可读，直到最后一步。

| 步骤 | 内容 | 验证 |
| --- | --- | --- |
| 1. 契约与词汇 | 定义 `experience-facts/v2`、存档说明 `notes` 和统一词汇；旧版本仍可读取，迁移后的记录在清理前对现有流程呈现原样 | 契约测试；旧记录读成新形状后，事实、来源、状态全部保留 |
| 2. 机械迁移 | 第三方事实移入背景资料；范围说明原样移入存档 `notes`（`pending`）；其余字段不变 | 迁移前后逐条对照：事实 ID、正文、来源、状态一一对应，数量守恒 |
| 3. 学历唯一来源 | 从简历资料、保留分组和答案合并出学历记录；有冲突时停下来问用户；删除其余副本，改为计算 | 资格检查、申请答案、简历学历都只读新记录；LaTeX 核对通过 |
| 4. 目录、匹配视图与整库匹配 | 重建经历目录（技能检索词、摘要，绑定内容版本）；生成匹配视图，接入整库一次匹配；超出上限时按目录选经历再发完整内容 | Hexagon 实测：时间、12 条判断与本次实验对比，引文核对全部通过 |
| 5. 按经历清理 | 模型依据原始来源提出建议，用户按经历批量确认：补状态、拆分 `agent_assisted`、把范围说明中的真实边界写成事实、把过程描述改写成事实 | 清理后的说明标为 `resolved`，修改记入经历历史；无法确定的保持 `unknown` |
| 6. 删除旧路径 | 删除旧标记、正则推断、多余学历副本和旧视图代码 | 全量测试；再次跑 Hexagon |

当前数据量：78 段经历，305 条事实（本人 155、第三方 130、团队 9、AI 相关 7、他人 4）。
第 2 步会把 130 条第三方事实移入背景资料；第 5 步需要处理 7 条 AI 相关事实和所有未知状态。

## 12. 待定事项

1. 申请信息库中的语言能力是否改为职业资料的一部分（现在作为自报答案保存）。
2. 现有派生的工作方向记录（`experience-organization/v1`）在写简历真正需要时再决定是否保留。
