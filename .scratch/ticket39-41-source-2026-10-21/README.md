# 39/40/41源码收尾

2026-10-21，Europe/Zurich。按用户明确要求推进三票源码；复用现有Pipeline、Flow、Worker、ResumeStore与Prism，不新增审核点。仅源码和隔离测试。App构建/更新/安装/启动、真实配置/邮箱/ATS申请继续暂停；最终Submit人工。

## 实际改动

- 39：新绑定仅存batch/job引用；Flow阶段、attempt、产物和历史保持。页面状态从Worker只读派生，GET/观察/页面命令不再双写页状态，也不由旧页副本决定Flow重开。材料更新采用也只保存引用。
- 材料复用读取材料记录，避免暂时读不到Worker使有效底稿/PDF失效。可识别旧页副本只在材料读取视图兼容；不批量改历史，不放宽实际材料资格校验。
- 40：复核共享完整生成、编译、导出、必要附稿、人工底稿及复用；交付[实际调用、兼容保留与逐项源码证据](materials-entrypoints.md)。保留有调用的Prism、准备模式、显式lab和handoff。
- 41：默认总览复用同一Pipeline/Flow只读状态，指向自动流程。保留显式handoff历史；修正准备模式导航。轮询保留同岗控件/焦点，历史查看可重新跟随当前及后续岗位。工具路径错误给出已有修正方法，资料仍可读。

## 证据与范围

- [源码基线](source-before.json)、[原tracker](tracker-before.json)及before-39/40/41原字节均保留。
- `state/`：39每个RED/GREEN、受影响回归和原文件；不改失败日志。
- [共享材料/入口逐项清单](materials-entrypoints.md)、[overview改动](overview/README.md)与`controls/`：41实际入口/控件失败与修复。
- 最终冻结输入、受影响/浏览器/完整默认结果、候选和逐项验收会在完成后记录于本目录。不将进行中的或部分运行称为通过。

固定PDF仅为测试传输；源码通过不等于真实材料文案/排版、主App安装组合、真实邮箱或雇主接收验收。原30/34及真实材料接受仍由原票持有。

## 集中待用户决定

本轮源码无须补充确认。后续只需决定何时恢复唯一主App更新与安装组合、何时恢复真实申请验证。当前两项继续暂停，不要求立即答复；普通材料、填写上传和一次Continue不增加例行批准。


## 首轮冻结结果与后继

首轮820项输入未变；受影响427通过、本地浏览器86通过。完整默认full-v1为8失败、4645通过、2跳过、572 deselected，未作为最终接受。五项是旧queued整对象断言，另有两项真实运行错误展示及一项不完整绑定读取崩溃。原日志、XML、候选v1和checked-inputs-v1原样保留；修复后须重冻并验证后继，未关闭三票。


## 最终源码版本 v2

最终源码于首轮失败修复后重新冻结，输入为checked-inputs-v2.json；当前checked-inputs.json与其相同。源码候选source-candidate-v2与首轮v1分别保留，不覆盖失败历史。最终统一结果及票据读回待运行结束后追加。

v5修复保留了关闭和runtime_error的原优先级；缺batch/job引用返回可读的needs_recheck/mismatch，不补造绑定ID。旧queued断言改为核对最新Worker状态及全部材料/revision保持。原owner、原页、intent、无自动重试断言保留；FullLaTeX原失败fixture未修改。三种损坏引用通过真实本地HTTP读取回归。实现阶段337项通过只作局部证据，最终以统一集合和完整结果为准。


## 最终统一结果与源码结案

| 范围 | 最终结果 | 原始结果 |
| --- | --- | --- |
| 完整默认离线 | 4656 passed, 2 skipped, 572 deselected in 931.45s (0:15:31) | [日志](full-v2.log)、[XML](full-v2.xml)、[回执](full-v2-run.json) |
| 受影响16模块 | 476 passed, 1 deselected in 101.73s (0:01:41) | [日志](affected-v2.log)、[XML](affected-v2.xml)、[回执](affected-v2-run.json) |
| 本地浏览器9模块 | 86 passed in 224.40s (0:03:44) | [日志](browser-v2.log)、[XML](browser-v2.xml)、[回执](browser-v2-run.json) |

集合有重叠，不相加。2项跳过的原名与原因见[跳过记录](skipped-v2.json)，没有将跳过计为通过。完整默认命令未添加marker覆盖；浏览器仅本地隔离页。原full-v1失败、其XML、旧候选和所有RED/GREEN原样保留。

最终[820项输入](checked-inputs-v2.json)与三轮运行各自before/after完全相同；[最终源码候选](source-candidate-v2/manifest.json)含426文件，ID为`preparation-candidate-3f68396549b88e53900c2c1d074d3737e0369fa4ec57875f19c7aed194c1ceb9`。[候选创建](candidate-create-v2.json)及[验证](candidate-verify-v2.json)均成功。相对入场814项的实际差异见[清单](source-delta-v2.json)和[补丁](source-delta-v2.diff)，五份操作文档另纳入冻结；没有修改Pipeline、Worker/Runner或原生App源码。全源Ruff检查/格式、两个JavaScript语法与git diff检查通过，见[静态记录](static-checks-v2.json)。

39的8项、40的7项及41的8项源码条件，分别按[状态归属矩阵](state-and-acceptance.md)和[材料/入口矩阵](materials-entrypoints.md)结案，原依赖、历史及本轮前原票字节均保留。状态变更与最终摘要见[源码结案回执](source-closeout.json)。历史记录中的“进行中”只表示当时快照；本节为最终交付。没有把源码结案扩展为30/34等票的安装或真实接受，也没有新增审批对象或流程。

本轮未构建、更新、安装或启动主App，未改真实运行配置、未读真实邮箱、未填写/上传/提交真实申请。固定PDF和隔离Swift/浏览器仅证明测试行为；实际材料文案、版式和雇主接收仍在原范围中。后续集中待决定仍只有恢复App更新、恢复真实申请的时机，当前继续暂停，无本轮新增确认项。
