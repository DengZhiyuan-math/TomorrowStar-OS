# 按实际原因显示资料准备状态：源码验证

2026-10-18。[按实际原因显示资料准备状态](../gmail-resume-preparation-2026-10-17/issues/20-source-readiness-reasons.md)由用户授权执行，前置来源核验已关闭。当前只更新源码与合成回归，不更新安装版；真实申请继续暂停。

## 修改

`application_preparation.py`复用现有profile、profile_issue及不可读文档错误，分别说明：

- 没有可用于材料准备的经历条目。
- 结构化个人资料缺失、格式无效或暂不可读。
- 其他文档超过读取上限、不是有效UTF-8文本，或暂不可读／未下载。
- 全部可读时沿用原来的来源归属审核提示。

个人资料有效时不再要求补齐；多个问题同时显示。提示采用固定文案，只按已有错误代码分类，不带出来源路径、字段值或异常正文。原source_status表达式与修改前AST一致，返回字段、读取上限、扫描范围、评分、资格、事实审核、材料确认与worker门槛不变。

## 测试过程

1. HTTP接口先复现有效profile加超限文档仍提示补齐个人资料；RED后最小修改转GREEN。
2. 按真实缺失／无效／不可读profile扩展HTTP用例；RED后分类原因转GREEN。
3. 核对无可用经历条目与profile状态独立，完整可读控制组保持available；新增反例先失败，再修正说明。
4. 同时放置超限和无效UTF-8文档，先复现遗漏具体格式原因，再修复原因合并；检查提示不泄漏合成私文案或路径。

所有新回归通过真实本地HTTP入口使用临时合成工作区，不读取私人资料。相关139项回归通过；独立只读复核确认无结案阻断，并单独执行准备入口17项通过。全仓Ruff检查通过，288文件格式检查通过；完整默认离线回归 **2748 passed / 276 deselected**，587.23s (0:09:47)；未覆盖live／live_model／worker_browser。

验证命令：

```sh
uv run --locked --offline --cache-dir /private/tmp/tomorrowstar-readiness-uv-cache python scripts/run_pytest.py -q tests/test_preparation_entry.py tests/test_preparation_snapshot_reuse.py tests/test_application_information.py tests/test_job_explanations.py tests/test_draft_flow.py tests/test_pdf_export_flow.py tests/test_catalog_document_cache.py tests/test_preparation_candidate_chain.py
uv run --locked --offline --cache-dir /private/tmp/tomorrowstar-readiness-uv-cache python scripts/run_pytest.py -q
uv run --locked --offline --cache-dir /private/tmp/tomorrowstar-readiness-uv-cache ruff check --no-cache --extend-exclude .scratch .
uv run --locked --offline --cache-dir /private/tmp/tomorrowstar-readiness-uv-cache ruff format --check --no-cache --extend-exclude .scratch .
git diff --check
```

默认uv缓存目录受限时改用上述临时缓存；首次缓存初始化失败不是产品测试失败。保留默认pytest marker排除，不调用live、live_model或worker_browser。

## 证据与后继

- [修改前文件清单](before-manifest.json)及before目录保留领取前原字节。
- [源码差异](application_preparation.patch)、[测试差异](test_preparation_entry.patch)只对照本轮原字节，不把checkout已有脏改动并入本次修改。
- [候选文件身份](candidate-files.json)绑定测试源码；[完整离线输出](offline.log)保留本轮结果。
- 当前候选的冻结、组合与安装复验仍由[核对当前安装候选的完整材料准备链](../gmail-resume-preparation-2026-10-17/issues/19-current-candidate-journey.md)持有。源码通过不代表安装已更新或用户接受。

既有私人资料、申请记录、暂停任务和历史证据不由本轮改写。没有刷新邮箱、调用真实模型、生成真实简历／PDF、填写、上传、Submit或恢复真实worker。

本票现已结案。[核对当前安装候选的完整材料准备链](../gmail-resume-preparation-2026-10-17/issues/19-current-candidate-journey.md)仍等待完整CV契约及其必要后继；后续任务未在本轮自动执行。
