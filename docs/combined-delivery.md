# 组合验证与后续交付准备

当前 JSON 主流程组合见[J08 分层验证](../.scratch/json-resume-delivery-2026-10-24/j08-verification.md)
和[JSON 实施地图](../.scratch/json-resume-delivery-2026-10-24/map.md)。
历史 P08 沿用[开发计划](development-plan.md)及其[实施地图](../.scratch/resume-agent-delivery-2026-10-22/map.md#p08-delivery)，
原记录见[P08 分层验证](../.scratch/resume-agent-delivery-2026-10-22/p08-source-verification.md)。
源码、录制组合、实际 subagents、临时 Prism、隔离 ATS、安装版和真实接受分别举证。

## J08 当前 JSON 组合

现有 ApplicationStore 的申请 JSON 进入正常两库读取与匹配，再交给逐经历 JSON
作者、程序校验、单一内容终审、固定模板渲染、采用和 PDF 导出，随后绑定 Worker。
新 Flow 任务保存 `material_contract="content-writing/v1"`；缺少结构化事实时停止，
不会创建旧 TeX 写作交接。旧持久任务与已存交接仍保留原契约。

样式、姓名、联系方式和教育是 LaTeX 模板原文。写作归档固定模板并绑定版本；
下一岗位默认复用原模板基线，跳过无槽位的历史成稿。首次绑定沿用生成项目策略，
允许已有根 Git，Git 元数据不进入源归档或编译依赖。

已绑定原页的 Prism 编辑先暂存候选草稿及实际 PDF，保留旧 Worker 材料绑定。
一次 Continue 核验原页、授权、输入和文件后采用候选，未知结果停止。发送前从
可信本地任务选定的信息库核对适用联系人与资格，固定模板资料不被逐岗覆盖。

源码与合成组合已接受；两位实际经历作者、独立终审及临时 Prism 当前工作树上的
原生编译、页面人工编辑单独举证。录制比较只检查固定输入下的流程与事实保全，
不能推断真实 provider 延迟或提速。私人真实申请、用户 Prism 服务、安装版及真实 ATS
未在本轮接受，原数据、人工修改和历史保留。

## 历史 P08 连通组合的范围

`tests/test_p08_combination.py` 从正常 `create_server`、Flow 和两库入口开始，
运行实际目录/按需读取/匹配代码，将固定结果交给写作、程序组装和单一终审。
同一任务进入 Prism 编辑返回，保留人工 TeX 与旧稿，再读取对应 PDF，使用真实
材料绑定进入 Worker。模型、快速校对和 Prism 回执在这组测试中是录制边界，
不作为真实模型或真实编译证据。

隔离浏览器组合继续使用同一材料和原页，保留 `check_single`。它核对实际上传
字节、非空人工值、空白填写、解析接续及最终提交边界；另以 PDF 篡改确认拒绝。
旧/新协议未知动作分别保留原申请、页面、意图与材料，不借 Continue 盲重放。

Quant 工程案例是通用等价合成接口回放。它检查经历名称不含能力词时仍从正文
发现、一次岗位说明、资料包贯穿写作、国家作用域和正常接续；不证明原真实申请私人资料、真实模型的金融业务判断或真实网站已经接受。原案例保留私人验收层。

组合初检修复了一处旧接缝：已交付的本地材料曾被裸职业库重扫拒绝，并将 P03
完整入口快照误当作选读快照。现在按任务保存的输入、已采用分析/草稿/导出和
实际 PDF 核验；目标 URL、授权、资格、执行占用、材料版本与字节检查仍执行。
旧 raw 材料继续采用其原当前输入规则，不把本轮修复扩成无条件放行。
适用联系人或 profile 页眉事实确有更正时，保留发送前的窄检查，核对当前材料
与更正事实后才再次传输；这项等待不作废旧 PDF，也不重扫全部经历。

## 历史 P08 实际编排与编译层

实际写作者由当前 Codex 的 subagent 工具分派，一经历一位作者。受控读取失败
只恢复失败作者；已成功片段保持。程序组装后交独立于作者的同一位内容终审，
采用字节与终审候选对应，省略与幂等采用分别检查。此层使用合成固定交付，
不把普通录制模型输出称为实际 subagent，也不证明私人简历质量。

真实 Prism 验证使用打补丁源码、独立临时状态与无 Git 项目，输入为上述实际
作者的采用稿。全部 provider 和自动更新关闭，浏览器只访问本机实例。原生
Tectonic 通过临时 PATH 包装追加 `--only-cached`，仅使用复制的资源缓存。
浏览器键盘编辑触发原有自动保存和自动编译，随后 `PrismClient.read_compiled`
仅 GET 读取对应回执及 PDF；不直接请求第二次 build。临时进程结束后关闭。
这证明临时候选服务和原生编译器的合成接缝，不表示用户服务已更新或接受。

## 复跑与记录

从 checkout 使用锁定环境；完整默认离线不加 `-m`。浏览器是独立 opt-in 运行，
不能将两轮数量相加称为一次完整结果。

```sh
uv run --locked --offline --no-sync python -B scripts/run_pytest.py -q tests/test_j08_flow_combination.py tests/test_j08_material_binding.py tests/test_j08_worker_information.py
uv run --locked --offline --no-sync python -B scripts/run_pytest.py -q -m worker_browser tests/test_j08_browser_combination.py
uv run --locked --offline --no-sync python -B scripts/run_pytest.py -q tests/test_p08_combination.py
uv run --locked --offline --no-sync python -B scripts/run_pytest.py -q -m worker_browser tests/test_p08_combination.py
uv run --locked --offline --no-sync python -B scripts/run_pytest.py -q
uv run --locked --offline --no-sync ruff check --no-cache --extend-exclude .scratch .
uv run --locked --offline --no-sync ruff format --check --no-cache --extend-exclude .scratch .
git diff --check
```

实际作者复跑使用[固定写作 API](resume-agent-operations.md)，不让 Python 模拟
启动作者。Prism 使用[当前结果契约](prism-resume-review.md)，从外部源码启动
独立临时项目服务并通过页面开启自动编译。复跑前核对引用清单中的补丁及来源，
状态、日志、回执和产物保存在隔离工作区；公库报告只保存 Boolean 结论。
最终完整运行前后核对源码、测试、锁文件和 Prism 补丁的同一候选，保留失败历史。
候选指纹用于交付复现，不成为日常材料的全局失效条件。

<a id="未来同步与接受"></a>
## 安装同步与后续接受

J08 不构建、安装或重启主 App。历史 P08 源码轮之后另获同步授权，并完成其
[安装版合成接受](../.scratch/resume-agent-delivery-2026-10-22/p01-p08-installed-verification.md)。
该记录只证明当时的安装候选，不代表本轮 JSON 源码已经安装。原签名、配置值、
状态和两库保留，真实申请继续暂停。后续同步与接受按以下层次记录：

1. 核对本轮候选与后续变更。若有新变更，只补适用检查并记录新的候选。
2. 按[唯一主 App 工作流](macos-app.md)和 `macos/main_app.py` 固定候选、备份、
   更新唯一 `~/Applications/TomorrowStar.app`，保留签名、配置、私人状态与回滚。
3. 对安装版另行接受；需要更新用户 Prism 服务时明确记录对应版本和服务结果，
   不把临时服务的成功当作该服务已更新。
4. 真实材料、真实申请原案例、ATS 行为及用户质量分别接受。自然人工 Submit 后才
   验证 APP-12 的实际结果与下一岗，不为测试强迫用户投递。

旧生成/安装交付、原工程票、负责人和依赖保持原范围。源码与组合准备完成不
关闭仍持有真实接受条件的旧票，也不宣称整链真实投递已完成。
