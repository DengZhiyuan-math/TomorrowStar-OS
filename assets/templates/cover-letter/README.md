# Cover Letter 独立模板

2026-10-25。单文件信件模板；仓库中的 `main.tex` 以占位符代替姓名、联系信息与自我介绍。
2026-10-28 起按用户决定，已填入已确认姓名与联系信息的个人模板只保存在私有工作区
`tomorrowstar-career-data/templates/cover-letter/main.tex`，不进入本仓库。固定称呼、自我介绍、结尾致谢及落款，岗位论证正文区留空。生成器、Flow 和 Worker 的源码接入见
[实施记录](../../../.scratch/cover-letter-integration-2026-10-25/implementation.md)；安装版未更新。

接入规划见[简历与 Cover Letter 同岗并发生成接入规划](../../../.scratch/cover-letter-integration-2026-10-25/map.md)。
同岗两路生成正文、独立保存与恢复；此模板只承担固定信件排版。

## 文件与版式

- `main.tex`：唯一模板，包含联系信息、申请信息、称呼、正文、结尾和落款。
  A4、11pt LaTeX 默认衬线字体、22mm 页边距。
  左对齐、段间留白、无首行缩进；姓名与联系信息置顶，下接细线、日期、招聘团队、
  日期和收件方可按实际需要填写；固定开头的准确岗位名由程序读取本次申请记录填入。
  无照片、图标、教育区块或单独的 Cover Letter 大标题。
- 正文可用多个段落展开一个或两个经历，不为每段加经历标题、技能标签或总结句。
- 开头自我介绍与结尾致谢保存在模板中，不逐岗调用模型重写。
  自我介绍复用已记录的姓名、博士在读身份、学校、研究方向与研究方法，形成一个完整段落；
  不随 JD 改写这些事实，不将博士在读写成已获学位，也不新增任职或能力判断。
- 自我介绍中的 `\LetterRoleTitle{}` 对应“apply for {}”的岗位空位，由程序使用已采用岗位的
  `role_title` 填入并进行 LaTeX 转义。模型不写这个空位；岗位名缺失时停止交付，
  不使用默认岗位。模板直接预览时的 `[Position title]` 不会作为申请输出交付。
- 文本框使用同一模板的称呼、自我介绍、岗位正文、致谢与落款；无需第二份文本模板。
- 仓库根目录的 `output/pdf/cover-letter-preview.pdf`：此前两个虚构经历的历史排版预览，
  不对应当前空白模板；当前源文件以编辑器自动编译预览为准。

11pt 正文和正常页边距保持可读性。整体通常控制在一页；内容过长时删减无关背景、
重复表述或重新分配两个经历的篇幅，不自动缩字、裁切或省略正文。
此前两个经历的合成样例仅验证版式容量，不要求每封信填满一页。

## 已确定的写作规则

写作、生成、复用和页面交付的完整约定统一见
[已确认的产品约定](../../../.scratch/cover-letter-integration-2026-10-25/PRD.md)。
本说明只持有模板的版式与编辑方法，避免维护第二份产品规则。

## 内容与交付边界

同一份语义正文用于文本和文件输出，保留人工修改与历史；由同一内容版本派生输出。
正文由 `application_cover_letter` 保存，LaTeX/PDF 是按需排版产物。
LaTeX 仅负责排版，不能成为第二份个人事实库。固定姓名、邮箱和适用联系链接
复用已确认记录；日期、收件方和岗位名随申请填写，不编造联系人。
个人模板包含联系信息，只保存在私有工作区，不作为公共合成测试夹具或默认安装资源。
通过私有 portal 配置 `cover_letter_template`、CLI `--cover-letter-template` 或
`TOMORROWSTAR_COVER_LETTER_TEMPLATE` 显式指定模板路径。

## 编辑与预览

私有副本已填入固定联系信息（仓库中的 `main.tex` 为占位符版本）；填写本次申请信息，并在
`BEGIN LETTER BODY` 与 `END LETTER BODY` 注释之间填写正文。
固定开头在 `BEGIN LETTER OPENING` 与 `END LETTER OPENING` 之间；固定致谢在正文区之后。
模型只写岗位动机与经历论证，不重复自我介绍、申请声明或结尾客套。
普通文本中的 `& % $ # _ { } ~ ^` 和反斜杠须按 LaTeX 规则转义；不把原始文本
直接当 LaTeX 执行。文本框版本保留普通字符，不带排版命令。

使用已存在的 Tectonic，在仓库根目录编译；中间产物留在临时目录：

```bash
mkdir -p /private/tmp/tomorrowstar-cover-letter-preview
tectonic -X compile --untrusted --keep-logs \
  --outdir /private/tmp/tomorrowstar-cover-letter-preview \
  assets/templates/cover-letter/main.tex
```

检查页数、编译警告、段落、链接和正文完整性，逐页渲染检查后再交付 PDF。
此模板不增加依赖、编译服务、页面自动化或材料审批步骤。
