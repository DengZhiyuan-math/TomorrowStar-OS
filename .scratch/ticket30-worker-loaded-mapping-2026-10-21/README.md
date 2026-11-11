# 30号票：worker完整加载映射与安装验证

## 最新完成结果 — 2026-10-21

用户随后明确授权同一路径更新、一次隔离worker验证及失败回滚。本轮已完成：**30号票当前8项均有适用证据，按当前合成验收范围结案。** 原负责人和依赖保留，真实申请继续暂停。以下较早的自动审批拒绝及待安装描述是前一回合记录，不代表当前停点。

### 实际加载及运行范围

- 最终安装为同一 `TomorrowStar.app`，固定证书与候选完整inventory核对通过；engine只变化一个worker启动文件，原生helper、依赖、controller/UI沿用原包。
- 实际安装worker的PID/run、原生App→后台→worker父链和独立合成根均已核对。其完整callable角色revision为 `python-loaded-code/v1:worker:aa85c1d4739ded7f9599eeb2ede8aa2e9179d97142045a845aa577b7b437cb53`，与安装manifest一致；`worker.package_mapping=verified`。33个启动源文件也逐项匹配，文件清单作为补充证据，不替代实际角色测量。
- 仅一个实际worker运行：初始化 → 固定Ashby posting/organization各一次 → 表单缺答案等待 → 暂停并只读观察原页。答案保持空、没有附件、intent为null；填写、上传及Submit为零。没有重演旧G0—G3或旧证明矩阵。
- readiness总体和旧compatibility诊断仍unknown、`can_fill=false`；本次不宣称整份readiness全绿或跨旧版本兼容全部通过。结论仅是实际worker包加载映射与上述实际运行范围。原G2/G3的null回执保持原字节，不回填。

### 首个夹具失败、实际回滚与后继

首个夹具由checkout Python生成，其固定CLI脚本头与安装版的包内Python不一致，被既有 `synthetic-browser-contract` 校验拒绝，后台退出2，未创建worker。失败根及原生退出日志保持；正常退出后，已按既有维护工具实际回滚原v3包并核对原inventory。随后用安装Python生成新根，先通过原校验，再安装同一个未变的签名候选完成上述唯一worker运行。没有放宽校验、改包来接受错误夹具或重放未知动作。

本次新worker在暂停且无intent时，经精确PID/run/命令行核对后正常SIGTERM退出；主App再正常Quit。新run/page/revision保留，观察时间可正常更新，不称新合成记录逐字不变。正式四根完整inventory、配置原字节、旧owner、未知结果与fill intent全部保持，旧null回执亦独立核验未变。本次App、后台、worker及页面owner均已退出；两次更新和中间实际回滚的六份备份均已核验。

### 结案依据

当前1—6项继续复用[上一轮逐项分层核对](../ticket30-installed-reconciliation-2026-10-21/README.md)，此次唯一启动import变化没有改变Runner业务路径；既有48项相关回归继续有效，没有重跑完整默认。当前7—8项由这次实际进程与安装映射补齐。独立只读审查确认这一结论，保留真实接受、历史旧版本及具体未运行平台边界；不关闭34或恢复真实申请。

实际证据：[运行结果](worker-result.json)、[活动进程映射](live-mapping-readback.json)、[最终安装和保全](final-install-readback.json)、[收尾](owned-worker-stop.json)、[结案读回](installed-verification.json)。本轮原始HTTP、进程、原生日志、错误根、正确根、截图和备份保存在同一私人证据根。公共界面图见[暂停的合成主App](installed-main-app.png)。

## 前一回合记录（保留）

2026-10-21，Europe/Zurich。用户要求补齐实际worker完整加载映射和运行范围，仅做必要有界验证，保留未知结果和fill intent，真实申请暂停。

**源码修复及隔离候选映射已验证；安装版最终验证尚未完成。** 更新同一主App的命令被自动审批审查拒绝，未执行。30保持claimed，当前7、8两项继续部分满足，原负责人和依赖不变。

## 原因与最小改动

现装v3的新鲜导入探针复现null：worker角色的 `application_readiness`、`application_single_binding` 尚未加载。显式加载这两个实际包模块后，完整callable revision与原manifest预期worker值一致，排除了本次缺口由归一化失败或摘要漂移引起。

[worker main](../../src/career_evidence_graph/application_worker_browser.py)现在在有效模式校验之后、store/start_run及一次性加载测量之前显式导入这两个角色模块。getter继续只读取已加载对象，没有新增权限或版本准入条件、API、业务状态或恢复机制。

[新鲜子进程回归](../../tests/test_worker_startup_loaded_identity.py)先准确RED于null断言，再GREEN；真实临时stores、PID/run和主入口均参与，浏览器前主动停止，没有替换加载测量函数。相关小集48通过，Ruff及格式检查通过。本次没有重跑完整默认或旧证明矩阵。

## 复用包与实际候选进程

私人候选复用当前已安装v3的全部依赖、原生helper、固定证书和原生输入。engine清单仅一个文件改变：`src/career_evidence_graph/application_worker_browser.py`；重测角色manifest并以原固定证书签名。候选扩展名为 `.bundle-candidate`，没有新增或注册App身份。

候选manifest SHA-256：`1e7ca91bd194cedfe98d77eac77b70b2093115d202f69aa6a889b73213f3f462`。

使用现装Python依赖执行候选真实 `main → start_run → loaded_runtime_revision`，得到绑定实际PID/run的非null完整角色revision，与候选manifest一致：

`python-loaded-code/v1:worker:aa85c1d4739ded7f9599eeb2ede8aa2e9179d97142045a845aa577b7b437cb53`

范围严格限worker初始化与加载测量：audit在首次Playwright driver子进程创建之前拒绝外部动作，没有替换worker函数。jobs/commands为空，浏览器、字段、上传与Submit均为零。exit 2是预期主动截止；原日志保留其Future异常，不描述成无异常退出或浏览器运行成功。

这证明候选真实代码的初始化映射，不证明安装主App已启动这个worker，也没有进入Runner/页面阶段。旧G2/G3的null保持原记录，不能回填。

## 自动审批拒绝及可审阅的后继操作

被拒动作是通过既有 `macos/main_app.py update` 将这个固定签名候选替换到唯一主App路径。自动审批给出的理由是：当前请求只明确授权有界验证，未明确授权安装变更，且隔离候选验证风险更低。命令未执行；未通过其他路径替换安装包。

其余工作已完成：单文件修复、48项相关回归、签名候选、真实候选初始化映射、固定Ashby隔离输入和前后保全检查均已准备好。

待明确批准的维护范围仅为：用既有维护工具备份并替换同一路径主App；在已准备的独立合成根启动一次worker，核对实际PID/run、完整角色revision和本次实际运行阶段，停在固定表单缺答案处。复用旧G0—G3和安装结果，不重新填传、不重跑旧矩阵。若该有界安装验证失败，保留原件并按既有工具回滚App包。

## 保全与剩余

前后完整清单确认：现装App字节与签名保持；正式四运行根完整inventory和配置原字节保持；旧owner、未知结果、fill intent、附件和profile未改。当前没有活主App或包内worker。真实申请继续暂停。

当前仅余批准后的安装进程映射及运行范围读回。该停点来自工具自动审批，不是新增的日常材料、Continue或申请审批。

原始RED/GREEN、48项日志、签名候选、探针、run记录和保全清单在本次私人证据根保留。公共读回见 [verification.json](verification.json)。本轮开始的票据/计划/地图和源码字节在 `before/` 保留；上一轮[6项满足、2项部分满足的分层核对](../ticket30-installed-reconciliation-2026-10-21/README.md)继续有效。
