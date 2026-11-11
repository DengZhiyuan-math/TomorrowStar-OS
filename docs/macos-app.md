# TomorrowStar macOS App

TomorrowStar 把职业工作台放入原生 macOS 窗口，内置 Python 和运行依赖。
当前产品设计以[单岗位流程](single-job-flow.md)为准；实现差异、顺序和验证工作见
[开发计划](development-plan.md)。本文的目标规范不代表当前安装包已经实现全部行为。
各日期的安装和测试记录分别说明实际范围，历史运行结果保持原样。

## 2026-10-25：v3 后继修复安装同步

当前[六项 v3 修复](../.scratch/v3-audit-repairs-2026-10-25/README.md)已在明确授权下同步至唯一主 App，见[安装验证记录](../.scratch/v3-audit-repairs-2026-10-25/installation.md)。安装引擎与已验证源码一致，固定签名和实际权限、配置、人工材料及已有任务保持，完整原包回退已验证。

候选与安装后包级验证、实际安装模块定向回归、复用现有 Chromium 的包内运行时合成流程、隔离原生窗口及正常退出检查通过，独立复核无遗留安装问题。没有真实模型、用户 Prism、ATS 或最终 Submit；验收后 App 保持关闭。下方各次安装记录保留原有时间与范围。

## 2026-10-25：审计修复安装同步

本轮[审计修复](../.scratch/audit-repair-plan-2026-10-25/implementation.md)已在后续明确授权下同步到唯一主 App，
详见[安装验证记录](../.scratch/audit-repair-plan-2026-10-25/installation.md)。安装包引擎与已验证源码一致。
固定签名身份与指定要求、更新前后的实际辅助功能及录屏权限、原配置、人工材料与已有任务均保留，完整回退已验证。

候选及安装后包级合成验证、实际安装模块的定向回归和独立复核通过。实际唯一主 App 的隔离合成材料窗口正常显示，
worker 关闭且未自动启动任务；退出后原生与后端进程均结束。验证没有连接真实模型、用户 Prism 或 ATS，没有真实申请或最终 Submit。
原安装及真实业务记录保留各自范围。

## 2026-10-25：新页资料复用安装同步

新页面按同一岗位记录复用材料和有来源的填写值，不要求恢复浏览器会话。
同一 Flow、终稿和人工文案保留；旧回读作为历史，新尝试重新核验页面及附件。
详见[新页填写 Interface](codex-handoff.md#浏览器关闭后的新页填写)。

完整默认回归、隔离浏览器回归、静态检查和执行清单一致性检查通过。
冻结版本已同步到唯一主 App，全部包内引擎文件与源码逐项一致。
固定证书与指定要求保持；更新前后实际辅助功能、录屏权限有效，未重置 TCC。
原包回退、配置原字节、申请记录及材料均已核验保留。

候选及安装后包级合成验证通过。实际唯一安装版的隔离原生窗口、记录新增／编辑／
读取／导出、已加载包身份及正常退出已核验；首次空白显示经原生刷新恢复，详情
弹窗用截图核验。随后按原 `--prepare-materials` 模式重开，自动 worker 保持关闭。

安装版配合 Codex 执行器完成真实申请的提交前现场核验。锁屏后由用户解锁，继续保留
同一任务、原 PDF 及三段人工文案；没有重新生成简历或编译，原 PDF 实际上传一次。
随后更正了可选 Cover Letter 的遗漏：以已确认资料起草求职信，通过网页
`Enter manually` 填入，全文回读后保存到同岗位记录；原有字段和简历附件保持。

当前填写与材料回读已保存为 `ready_for_review`，最终 Submit 未执行。
本次未验证提交时的服务端校验、验证码或默认 worker 独立自动闭环。
各阶段现场耗时、锁屏等待及遗漏更正分别记录；现场时间包含 Codex 推理、工具和
界面操作，不能作为 App 后端或网络请求的纯耗时。通用 Cover Letter 模板和生成规则
尚未交付，已列入[后续工作](development-plan.md#cover-letter-followup-2026-10-25)。

## 2026-10-25：代码审计整理安装同步

根据后续安装授权，[代码审计整理](codebase-responsibilities.md#2026-10-25高频读取与调度复核)
的最终已测源码已同步至唯一主 App。安装包的全部引擎文件与该源码逐项一致。
原固定证书和指定要求保持一致；更新前后实际辅助功能、录屏权限均有效，未重新授权
或重置 TCC。维护入口保留了完整原包回退，原配置字节、申请记录和任务状态保持。

安装前候选和安装后包级合成验证均通过。另从实际唯一安装路径启动合成材料窗口，
核验页面、静态资源、已加载代码身份、记录新建／编辑／读取／导出及窗口回显；
正常退出后，原生窗口与后台进程均结束。包级重定位验证与实际原生窗口结果分别记录。

验收后已按原 `--prepare-materials` 模式重开。原任务和历史 PDF 保留，worker 与后台
自动申请关闭。本次未调用真实模型、访问 ATS、上传真实材料或执行最终 Submit；
历史上传报告不构成本次上传或材料质量验收。下文旧安装记录继续保留其原有范围。

## P01–P08 安装同步

已按后续授权固定已验证的生产候选并更新唯一主 App，见[安装验证](../.scratch/resume-agent-delivery-2026-10-22/p01-p08-installed-verification.md)。固定签名、配置值、原任务、私人数据及回滚保留。安装版合成检查通过，正式窗口显式以 `--prepare-materials` 重开，worker 与自动申请后台关闭。真实申请继续暂停，最终 Submit 手动。用户 Prism 服务与私人材料质量接受另记。

## 先前简历修改的限定安装同步

本轮已完成紧凑教育模板及 HTML 简历入口退役的限定安装同步，见[安装核验](../.scratch/latex-template-installed-2026-10-23/README.md)。唯一主 App 已重开，连接设置与原任务保留；真实申请继续暂停。该记录只更新所列简历改动的安装状态，不扩大其他并行工作或真实申请的执行权限。

## 当前流程

普通入口为自动申请，`--prepare-materials` 保留独立材料准备入口。
系统持续收录推荐邮件，复用已经保存的岗位和资料。用户启动后，严格一次处理一个岗位：
取得完整 JD、分析匹配，再按[APP-06 匹配路由](single-job-flow.md#可验证要求)处理：
分数过低的岗位记录跳过原因后继续；普通岗位自动生成、检查专用简历及必要材料，填写和上传；
高价值且高匹配的岗位先完成分析与材料初稿，再提示用户精准调整，改完一次继续填写和上传。
需要投递的岗位最后等待用户在原页最终 Submit。
系统自动观察提交结果，确认结果后继续下一岗；结果不明时停在当前岗询问。

重要必要事实缺失、实际冲突或操作结果不明时，保留当前岗位、页面和用户编辑，等待回应。
只有用户选择跳过才进入下一岗。等待期间可收录新邮件，不分析、生成或填写其他岗位。
没有整轮时限、每轮邮件数或岗位数硬上限；单次操作超时或没有进展时报告具体原因。

回答一次后按适用范围保存到信息库；职业事实和直接更正保存在职业库。
使用适用的已有资料无需重复确认。资格未知不阻止取得 JD、分析或准备材料；真正需要
该事实的步骤才等待。资料变化只更新受影响的结果，不因全局指纹或登录配置变化作废所有材料。
最终 PDF、来源、差异及版式检查由系统处理，用户可以查看和更正；不要求逐组、逐 PDF 再审批。

正常开启的流程在重开后自动检查进度并继续。显式暂停、用户等待和已取消状态保持原意。
系统先读取当前页面，保留手动编辑，再继续下一必要操作；未知动作不盲目重放。
登录、验证或控件需要用户处理时，完成后只需一次“继续”，不另要求保存核验结论、重新接管再开始。

通用浏览器正常使用网站的读取、导航、自动保存和附件上传；平台或网络请求 grant 不作产品前置。
实际辅助功能或录屏权限只约束依赖这些能力的操作，本地资料保存、匹配分析不因此被阻塞。
包哈希、加载版本、权限证明、epoch 和控制租约保留作排错信息，不形成日常使用的审批流程。
主 App 的稳定签名和单一安装身份继续作为维护约束，详见下方构建说明。

## 打开与连接数据

1. 双击唯一的 `~/Applications/TomorrowStar.app`。
2. 复用已有 `~/Library/Application Support/TomorrowStar/portal.json`。
3. 初次选择投递记录目录与独立的私人 career-data Git 仓库。
4. 修改目录使用 `TomorrowStar → 数据文件夹…`（`⌘,`）。

记录保存在所选目录，个人数据不复制到安装包。现有私人仓库检查使用 `/usr/bin/git`。
可在选择器中新建投递目录；职业证据仓库沿用既有目录。
现有可选配置 `preparation_root` 用于独立材料准备记录，通过
`--config /absolute/private/config.json` 指定；它不改变默认申请流程或已保存任务的控制状态。
配置无效应报告具体路径问题，不应另造业务批准。

源码新增 `TomorrowStar → 邮件处理…`。填写可选的 Gmail 专用处理标签，保存后重新打开
工作台生效。保存设置本身不重启后台，也不推进岗位。标签按输入原值保存；清空并保存
则关闭标记和归档，仍可读取资料、收录邮件及候选。不要填写 INBOX、TRASH 等系统标签。
坏标签只显示邮件处理配置错误，不要求重选资料目录。

该设置沿用 `portal.json` 的可选字符串 `application_processed_label`，经原生启动参数
`--application-processed-label=<原值>`、`macos/server.py` 和
`create_server(application_processed_label=...)` 传给 Intake 的 `processed_label`。
缺失或 null 表示未配置；错误 JSON 类型局部禁用标记/归档。普通标签由既有邮件处理接口
在完整收录落盘后使用，不预建真实标签。
含 NUL 或 UTF-8 超过 65,536 字节的配置字符串保留在配置中，但启动时传递空串无效哨兵，
避免操作系统在 Python 校验前拒绝整个后台进程。

默认邮件卡片分别显示本地收录、已标记、已归档、待核对和 JD 获取进度。
`GET /api/recommendations/state`（也可用 `/api/intake/state`）的 `progress` 包含
`mail_captured`、`mail_labeled`、`mail_archived`、`mail_needs_recheck`、
`mail_label_configured`、`mail_processing_error` 与既有 `source_*` 字段。
这些 GET 只观察状态；邮件处理完成不代表岗位分析或申请完成。

以上为源码能力；当前安装范围以本页 P01–P08 安装记录为准，未执行真实邮件标记或归档。真实申请继续暂停；
原源码与合成验证交接见[邮件设置实施记录](../.scratch/mail-settings-implementation-2026-10-21/README.md)。

## 现有入口与实现范围

| 入口 | 用途 |
| --- | --- |
| 今日工作／岗位工作区 | 当前岗位、等待原因和下一必要操作 |
| 岗位与进度 | 搜索、新增、编辑、证据和 CSV 导出 |
| 材料准备 | 独立分析和简历准备入口；不代替默认自动申请 |
| 职业证据 | 文档、关系图谱和来源 |
| 项目访谈 | 三层访谈预览和研究评估规范 |
| 公开展示 | [网站内容](public-website.md)预览；公开发布单独处理 |
| 简历审阅（Prism） | `⌘8` 查看、编辑完整源及 PDF；保留历史 |
| 原生窗口 | 文件选择、复制粘贴、窗口管理及外部链接 |

菜单和已有备用入口不保证主链已经跑通。当前实现的阶段按钮、逐组审阅、恢复和发送
限制应按开发计划收敛，不能把这些旧操作步骤重新解释为用户的目标流程。
现有 `⌘1` 打开岗位工作区，`⌘R` 刷新，`⌘W` 或 `⌘Q` 退出。
离开前保留未保存的投递编辑；退出关闭本次 App 的服务，重开依据保存的控制状态恢复。
服务仅监听 loopback 临时端口。保存状态与正常恢复不依赖某个 WebView 路由持续可见。

岗位简历生成使用已有 Codex CLI，依次查找 PATH 和用户／系统 Applications 下的内置 CLI。
现有 `TOMORROWSTAR_CODEX_EXECUTABLE` 或后端 `--codex-executable` 可指定可执行文件。
依赖、登录和额度检查用于识别实际故障；正常的已启动流程无需逐阶段重新批准模型调用。
缺少某个依赖时，只暂停需要它的操作，已有记录和其他可用功能仍可使用。

信息库的基础事实、国家、公司及单岗位限定答案保留各自范围。简历采用职业库中的教育、
日期、经历及责任事实；不能把 Job Apply 配置、信息库和职业库当成相互竞争的事实库。
真实冲突应向用户说明，用户直接更正后保存并更新受影响材料。研究 inventory seal、Grill-Me
和 Skill 评分仍有各自证据规则，不阻止一般事实保存或正常求职资料复用。

旧 Prism 草稿、具体 PDF 和原来源继续可检查。实际编译/导出失败应显示原因；结果未知时
自动读取已有本地回执，仍无法确定才停当前任务询问。无需让用户承担回执审批工作。
生成、校验、保存和逐岗完整主链的剩余实现见开发计划；不得把固定 PDF 合成测试当成真实简历质量。

## 历史后台申请 worker

以下保留 2026-10-13 构建的历史行为及验收记录。当前默认入口以上文为准；
原有运行目录与暂停记录保持，不自动迁移到新的交接目录。

2026-10-13 构建默认启用后台 Cua worker。
打开 App 只创建服务；准备批次或继续批次时才启动 worker。
复用 `~/Library/Application Support/TomorrowStar/application-worker` 中的 live 状态、确认答案和附件。
浏览器从初始化起隐藏，只有点击人工复核才显示原页面。最终 Submit 仍由用户操作。

App 内置已有 Playwright、pyee、greenlet 和 worker 启动器。
系统 Chrome 是外部运行时；修复包使用内置 Cua 辅助程序，缺失、哈希不符或权限不足时停止。
简历 PDF 导出也使用系统 Chrome，运行在独立的无头临时配置中，离线并阻断所有页面请求。
它不依赖 Playwright 下载的 Chromium。原生包验证会用包内 Python 实际导出合成 PDF。
本轮安装没有启动应用、重启 worker 或修改当前连接设置。
记录见[应用更新验收](../.scratch/cua-app-update-2026-10-13/README.md)；执行边界见[Cua 说明](cua-worker.md)。

2026-10-13 的[故障原页与缓存后继更新](../.scratch/worker-handoff-app-update-2026-10-13/README.md)已安装到本机应用。
原页仍可定位时，worker 停在当前问题处等待人工确认。工作台提供“定位原页并核验”；未知结果先保存具体结论与来源，再明确允许自动层接管。暂停批次不会因保存答案自动恢复。
本次更新保留原应用完整备份、暂停检查点和附件，没有启动 App 或重启现有 worker、浏览器。下一次打开 App 时加载新代码；历史页面记录不证明原页面仍有效。

## 构建与验证

以下记录现有验收工具和兼容性入口。工具仍含早期分阶段操作时，按
[开发计划](development-plan.md)修改验证流程；不把测试夹具的逐组审核、暂停或
显式重试规则作为正常产品使用前提。历史通过/失败结论保持原记录。

材料准备安装验收使用唯一主 App 及独立合成目录。先用包内 Python 执行
`scripts/create_synthetic_flow.py --preparation /absolute/new/root`，再以
`--synthetic-preparation /absolute/new/root` 启动该候选。此模式使用固定邮箱、完整
JD 和模型替身，并提供 Git 外的完整 LaTeX 底稿、已确认合成身份及固定预览 PDF。
显式绑定 `latex-base/main.tex` 后，新完整链复用字面来源，经逐组审核再绑定具体
PDF，系统校验后自动保存材料绑定。完整链的 Prism 打开入口明确拒绝真实连接，编译替身
仅返回所核验的固定 PDF；它验证回执及状态，不证明当前 LaTeX 的实际编译或版式。
可在材料页使用已有分组编辑入口。旧摘要路径仍沿用原 PDF renderer。
准备任务、信息库、HOME 和临时文件均限定在合成目录，不构造填写 worker。
该参数不与其他配置或启动模式混用；重开只恢复保存进度，不自动执行任何阶段。
普通默认入口仍使用原连接，因此合成验收必须保留这个明确启动参数。
填写中补充信息并离开输入框后，系统自动保存到信息库；选项变更后直接保存。
基础事实和岗位、国家等限定答案保持各自范围。保存不恢复暂停的填写，未知结果不自动重发。
源码冻结、打包、安装窗口流程、冷启动和 PDF 版面各自记录；合成通过不代表真实
材料质量接受。安装和回退只使用唯一的主 App；私人目录和暂停任务保持原状。

在 Apple Silicon macOS 的已锁定项目环境中运行：

```sh
uv run --locked python macos/build.py --cua-driver /absolute/path/to/reviewed/cua-driver
uv run --locked python macos/verify.py \
  --app "$HOME/Library/Application Support/TomorrowStar/builds.noindex/TomorrowStar.bundle-candidate" \
  --report /absolute/private/new-acceptance.json
```

唯一安装位置为 `~/Applications/TomorrowStar.app`，固定 bundle ID 为
`dev.tomorrowstar.desktop`。不要创建或注册其他测试 App。
构建默认只在私人 `~/Library/Application Support/TomorrowStar/builds.noindex/`
产生 `TomorrowStar.bundle-candidate`；已有目标会被拒绝。该文件是未安装的软件包，
不能作为另一个 App 打开。更新主 App 前保留私人回退副本，并核对主 App 已退出。

日常维护入口为 `macos/main_app.py`：

```sh
uv run --locked python macos/main_app.py check --private-root /absolute/private/new-signing-check
uv run --locked python macos/main_app.py update \
  --candidate "$HOME/Library/Application Support/TomorrowStar/builds.noindex/TomorrowStar.bundle-candidate" \
  --private-root /absolute/private/new-update-record
uv run --locked python macos/check_main_permissions.py \
  --private-root /absolute/private/new-permission-check
```

每个 `--private-root` 都必须是尚不存在的私人目录。`check` 验证签名身份；
权限检查只启动固定主 App 的无窗口诊断，不提示授权、不创建浏览器或读取普通任务。
权限检查退出码 `0` 表示两项实际授权均有效，`2` 表示仍缺授权；其他失败需要检查证据。
更新前确认主 App 及其进程已退出。维护程序先核验并保存回退，再验证私有暂存副本，
最后替换唯一安装路径。主 App 或候选的证书／指定要求不同就停止，不代替用户轮换身份。
`migrate-signature` 仅用于历史 ad-hoc 主 App 的一次性迁移，日常开发不重复执行。
编写代码和离线测试不需要重新授权；需要原生权限的检查才核对实际宿主授权。

构建器先读取私人 `~/Library/Application Support/TomorrowStar/signing.json`，
要求其中 `identity_sha1` 为已验证、可用的签名证书 SHA-1，`installed_app` 为固定主 App，
`designated_requirement` 同时绑定固定 bundle ID 和该证书。源码库不保存证书或私钥。
主 App 的严格签名、指定要求或证书可用性不符时，在创建构建目录之前停止。
`--signing-identity` 只允许重复指定已固定的同一个 SHA-1，不能隐式轮换证书。
缺少配置或签名失败时不会回退到临时签名。外层 App 和自有原生组件使用固定证书，
经审阅的 Cua 辅助程序继续保留其原签名字节。安装器也须验证同一个指定要求，
需要诊断权限时从主 App 做不弹窗的实际权限检查。系统策略和用户撤销仍可能使权限失效；
代码签名连续性不能替代真实操作所需的授权。责任链探针与包版本检查不作每岗审批。

`--allow-ad-hoc-synthetic` 仅为显式隔离的软件包合成测试保留，也只允许
`.bundle-candidate` 输出，拒绝所有新增 `.app` 和 Applications 内的目标。
不能用于更新安装版、权限验收或修复授权。日常构建不使用该参数。
`--cua-driver` 必须指向已复验的固定构建；构建器保留其签名字节并附带 MIT 许可证与来源。
验收报告也采用创建一次的方式写入。整个构建过程不下载依赖。
构建需要 Xcode Command Line Tools 的 Swift、AppKit、WebKit 和 `codesign`。
`macos/Icon.swift` 保留图标生成源；构建复用 `macos/icons/AppIcon.icns`。

安装包只包含显式选定的引擎代码、静态页面、流程规范、运行时和许可证。
`Contents/Resources/build-manifest.json` 记录公开源文件摘要和依赖版本。
构建从当前工作目录的代码生成，包含已验收但尚未提交的本地改动。
源仓库、私人脚本、私人记录和测试夹具不会进入 App。

验收脚本会把 App 复制到源码目录之外的临时路径，并从 `/` 启动内置 Python。
脚本只使用合成数据。它检查应用新增、编辑、导出、证据读取、图谱、流程规范、
Host/CSRF 防护、源文件摘要和关闭控制管道后的退出行为。
验证器应分别覆盖默认自动申请入口与显式 `--prepare-materials` 材料准备入口，
使用合成记录，不访问 ATS。旧报告中“默认材料准备”与“仅显式单岗填写”的
`launch_modes` 是当时入口结果，不定义当前默认行为。对验证器的调整与新结果须
单独记录；原安装包、私人记录和历史版本不因本文修订而改变。
默认测试仍使用仓库启动器：

```sh
uv run --locked python scripts/run_pytest.py -q
uv run --locked ruff check .
uv run --locked ruff format --check .
```

当前主安装版已迁移到固定的本地代码签名证书，信任仅限当前用户的 CodeSigning 用途。
证书身份和指定要求保存在私人配置中，后续开发复用同一个身份，不重复生成证书。
这不是 Developer ID 分发签名或 Apple 公证；对外发布仍沿用独立的发布流程。

2026-10-16 的[包内驱动接入与安装验收](../.scratch/cua-installed-integration-2026-10-16/README.md)
保留完整原包回退，未启动应用窗口或重启现有 worker。实际包内运行时完成隔离合成验证。
本轮只读权限值属于测试调用宿主，未单独验证 GUI 宿主的 TCC；没有请求新权限或切前台。

以下为 2026-10-16 的历史快照。后继的[原生宿主独立核验](../.scratch/cua-gui-host-tcc-2026-10-16/README.md)已通过实际安装路径执行。
原生入口支持 `--background-check gui-host-<唯一标记>`：在创建窗口或读取私人配置前选择
禁止激活的诊断模式，只运行包内固定脚本，输出到新建的私有 0700 诊断目录。
它只读取 TCC 状态，不请求授权。原生宿主及整个辅助进程责任链均指向 TomorrowStar；
本轮辅助功能、录屏均未授予，实际后台调用按原守卫停止，未创建浏览器。
当前结果属于本轮重新本地签名后的安装身份，不能推断历史签名的授权状态。
仍保留完整原包回退；没有打开权限设置，GUI 完整附着验收仍待授权后进行。

2026-10-09 的构建位于 `build/macos/release/TomorrowStar.app`。
验收报告位于同一目录。详细结果见 [本机验收记录](macos-app-acceptance-2026-10-09.md)。

2026-10-10 的网站整合构建位于
`build/macos/website-integration-2026-10-10/TomorrowStar.app`。
同目录提供 `TomorrowStar-macOS-arm64.zip` 和 `acceptance.json`。
合成数据复验已通过公开展示读取、搬移启动、内置运行时和读取后的严格签名检查。
该次验证时未替换安装，新窗口交互尚待验收；当前状态见上方执行地图。

2026-10-17 的原页恢复修正版使用独立安装身份
`dev.tomorrowstar.desktop.page-recovery`。标准构建和恢复副本的 manifest、
Info.plist 与签名分别绑定，见[恢复验证记录](../.scratch/single-job-application-flow-2026-10-16/assets/retained-page-recovery-verification-20261017.json)。
恢复副本已通过隔离包验证、完整默认离线测试和原生原页交接；它只向现有运行请求 review。
没有 flow 所有权时，其余写操作仍拒绝。原 App、原 bundle、worker 及权限责任链保持原位。

恢复服务与实际浏览器执行器是不同版本。不要退出原执行宿主或替换其 bundle 来制造恢复；
不要对这个不同 bundle ID 的副本套用标准宿主身份诊断并据此推断权限。
交接完成仅证明原页已交出；原页内容、明确 recheck、真实字段和附件仍需分别核验。

## 模块与原生接口

`macos/App.swift` 管理窗口、菜单、文件选择、下载和子进程。
`macos/server.py` 只负责启动现有服务及响应父进程退出。
引擎、数据校验和 HTTP 防护继续复用 `career_evidence_graph.career_portal`。

文件上传使用 Apple 的 [WKUIDelegate 文件选择接口](https://developer.apple.com/documentation/webkit/wkuidelegate/webview(_:runopenpanelwith:initiatedbyframe:completionhandler:))。
CSV 使用 [WKDownload 目标接口](https://developer.apple.com/documentation/webkit/wkdownloaddelegate/download(_:decidedestinationusing:suggestedfilename:completionhandler:))。
下载先写入独立临时文件，完成后写入用户选定的目标，支持原生保存窗口中的替换选择。
