# 邮件处理设置、独立进度与 Ashby 初始化源码交接

2026-10-21，Europe/Zurich。按 implement 推进P0票42与并行P1票33。保留原工作区未提交修改；没有commit/push。唯一主App未更新或启动，真实邮箱与真实申请仍暂停，最终Submit人工。

## 源码结果

- 原生现有菜单新增“邮件处理…”，沿用原 `portal.json`；保存可选 `application_processed_label`，重开沿用。正常字符串包含前导/尾随空白、前导 `--` 均按原值传递，不预设标签。保存不重启后台或推进岗位。
- Native → `--application-processed-label=<原值>` → server → `create_server(application_processed_label=...)` → Intake `processed_label`。未配置仍可资料读取/收录，不执行标记归档。错误类型、NUL、过长argv字符串不会误报资料目录故障；Intake坏标签回退到收录能力，并通过 `progress.mail_processing_error` 报局部错误。
- 默认邮件卡片分别显示本地收录、已标记、已归档、待核对，保留独立JD获取计数。轮询不发POST，不丢未保存答案/焦点，不启动下一岗；未知归档先inspect，不重复派发。
- Ashby复用原DraftSession及真实Runner，补公开organization读取与官方Query的fragment结构，按根字段和同岗位/组织变量确定用途；Query名称/选择字段变化无需新grant。响应别名回读正确，不放宽mutation、上传或最终Submit。详见[33号票源码报告](../ashby-bootstrap-2026-10-21/README.md)。

没有新依赖、状态库、权限服务、邮件系统或另一App。未重试历史未知open。

## 配置与使用

[用户操作和JSON调用清单](../../docs/macos-app.md#打开与连接数据)。新增字段只在后续安装更新后可用。缺失/null为未配置；设置界面清空保存删除标签配置；非法原配置类型传空串哨兵，合法原值不裁剪。含NUL或UTF-8超过65,536字节的原字符串在配置中保留，仅进程参数使用无效空串哨兵。

`GET /api/recommendations/state`及`GET /api/intake/state`返回`progress.mail_captured / mail_labeled / mail_archived / mail_needs_recheck / mail_label_configured / mail_processing_error`和既有`source_*`；GET只读。普通收录仍用已认证`POST /api/recommendations/refresh`的`capture_only: true`；未知结果通过既有带revision的continue入口先核对。没有新增HTTP写接口。

## 验证与修正

- [HTTP RED](http-red.txt)：4失败/1通过，原因是生产create_server不接受配置参数；[受影响HTTP/Intake集合](http-green.txt)：176通过。覆盖配置原值、未配置、坏配置局部错误、重开、账号/原邮件/候选保留、完整落盘后才处理及未知结果不重发。
- [默认浏览器RED](browser-red.log)：4失败；[GREEN](browser-green.log)：4通过；[相关浏览器](browser-regression.log)：14通过。原sandbox Chromium启动失败只是环境失败，行为RED来自后续获准隔离浏览器运行。仅本地/离线合成输入。
- [Native收据](native/receipt.json)：先RED，设置用例最终15通过，包含NUL与262,144字符坏配置。原整文件144通过发生在最后新增两例之前，最终完整默认运行将覆盖这两例；不把摘要或摘录冒充完整raw日志。
- 独立review发现启动保存旧配置可能覆盖刚保存的新标签，随后限定后台ready后才能打开标签设置。readiness回调在主线程先设address、同步保存旧workspace后才加载页面；保存设置也在主线程，消除了该交错。另用既有checkingChanges和attachedSheet互斥文件夹/邮件设置，防止排队sheet持有旧Workspace。独立复查确认两项均关闭，无未解决发现。[复核记录](review.md)。
- `full-v1`和`full-v2`分别主动中断以采用两个review修正，退出130；[v1原因](full-v1-interruption.json)、[v2原因](full-v2-interruption.json)及原日志保留，不计完整通过。最终完整默认[full-v3](full-v3-run.json)已通过：4597 passed、2 skipped、561 deselected，966.33s；811项输入前后无变化。原[日志](full-v3.log)与[JUnit](full-v3.xml)保留。两个[跳过原因](skipped-tests.json)均为显式opt-in渲染/性能benchmark。
- 额外默认入口/Ashby/Submit浏览器组合[43通过](browser-final.log)，24 deselected，144.68s；此后仅Swift设置互斥守卫变化，浏览器消费源码保持相同。最终源码Swift typecheck与全仓Ruff check/format通过，见typecheck-v3.log、lint-v3-run.json与format-v3-run.json。完整默认与额外浏览器结果不相加；最终来源/测试已通过，安装与真实接受未运行。

## 同一候选的后续安装准备

[最小安装旅程、支持/未支持矩阵与恢复/回滚](minimal-installed-journey.md)。当前最终源码候选为[source-candidate-v4/manifest.json](source-candidate-v4/manifest.json)，422项。它只复制公开源码与合成验证输入，不构建/安装App，也不是独立完整测试checkout。

[source-delta-v4.json](source-delta-v4.json)相对上轮808项冻结共14个登记路径变化，包含6生产文件、6测试文件及README/用户文档；README也保留本次开始前已有的导航修改。开发计划和原票交接单独更新。完整运行后仅README导航文档变化，生产/测试未变，见[最终文档差异证明](post-verification-docs.json)。v1/v2候选在review修正完成前创建，v3使用最终源码但还没有完整通过后的README导航更新；均保留为历史，最终交付使用v4。

## 原票交接与限制

42按有限源码与合成范围关闭；原35票继续持有邮件后端/账号/收据及真实标签归档整体验收，原41票持有默认入口整体体验。33仍保留安装/真实初始化与原unknown-open边界，不用合成通过补勾旧真实验收。28/30承接单一App候选安装；34/37/11继续持有组合/自然手动Submit和真实接受。

本批未接受真实材料质量、雇主接收、任意SSO或任意平台兼容；未操作真实标签、上传或Submit。用户后续许可前不执行安装与真实申请。

[App只读核对](app-readback-final.json)：1465个登记普通文件与原清单完全相同。初次枚举跟随了两个pkgconfig符号链接，原清单不计链接；按原规则重查后文件集合和hash一致。没有执行App写入。

最终交付：42源码票closed，33仍claimed、Triage为source-verified-awaiting-real-acceptance。35/41状态和负责人保持，仅追加交接；完整结果不关闭这些原整票。最终tracker与输入/文档读回见final-readback.json。
