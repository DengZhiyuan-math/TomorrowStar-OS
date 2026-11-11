# 浏览器候选组合与安装复验

2026-10-18 最新：08独立安装合成工程复验已结案。两份新PDF测试授权已执行；manual停止、unknown原页/完整intent保留，界面重绘竞态最小修复后manual_stop保存及再次App冷重开通过。[最终报告](branches-authorized/README.md)、[机器核验](branches-authorized/verification-final.json)、[独立终审](branches-authorized/independent-audit.md)。后继候选aea59ef4…6216完整默认离线2555/270排除、11浏览器通过；Python/helper字节不变、旧worker未升级，实际管理状态仍unknown，不宣称恢复执行。真实审核/申请及09用户接受保持暂停。

以下原组合与前驱安装进度为历史，链接和失败证据保留。

组合票07已完成：[五对及异常证据](comparison/README.md)、[组合验证](composition-verification.json)、[独立审查](review/composition-review-v1.json)。安装票08仍部分完成：原[待审部分证据](installed-partial-verification.json)与[独立部分审查](review/installed-partial-review.json)保留。用户后续明确授权原DOM PDF测试确认，已完成一行合成启动修复、完整2555离线回归、安装三字段填写与原页接管；App冷重开无重放，但新后台控制连接仍未知。manual/unknown两份新合成PDF均待测试确认，人工接受未完成。见[本轮后继报告](continuation-authorized/README.md)。真实申请继续暂停。

原组合候选为 `preparation-candidate-4809f86764eeb9b4e68990f087f874268ca21b66d68fb2b729e318d3896b45b5`；本轮后继安装候选为 `preparation-candidate-65f58a093c583b643f1d152a63b4bc0ec2df7e86f49e5628593f30bf9cfc1711`。沿用现有冻结工具，因此保留该工具的候选ID前缀；这不是用户接受准备版的声明。以下链接保留原组合和原安装证据，后继安装身份及完整新证据在上方本轮报告。

- [候选选择](candidate-selection.json)：仅忙闲调度、窄DOM下拉框、派发前选路；严格合成入口只作验收。缓存、快照query及新浏览器JD适配均未纳入。
- [源码门槛](../browser-efficiency-execution-2026-10-18/routing-gate/verification.json)：2554默认离线及86浏览器通过；245个公共文件与冻结包逐项一致。未改公共源码则复用这一准确版本的门槛。
- [独立暂存包核验](staged-package.json)：75个引擎文件、原生输入、真实helper哈希与deep/strict签名通过；[签名前后身份](package-identity.json)分别保留。
- [事先声明的比较与安装计划](../browser-efficiency-execution-2026-10-18/composed-validation-plan.md)：实际helper、同输入同终点、独立oracle、五对对照及异常保留。
- [统一待审核清单](../tomorrowstar-delivery-2026-10-17/review-queue.md)：真实材料质量、准备版接受和浏览器体验留给用户之后集中审核。

独立安装版为 `TomorrowStar Browser Verified.app`，bundle ID `dev.tomorrowstar.desktop.browser-acceptance-v1-20261018`；合成验收明确指定 `--synthetic-browser`。[安装读回](installed-package.json)及[运行后签名](installed-package-after-run.json)通过。原两个App、先前Preparation Verified版本、九项私人runtime元数据[均与基线一致](preservation-after.json)。普通入口不能当合成隔离入口使用。
