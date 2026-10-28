# 单岗简历草稿实现与验证

对应[生成并审阅单岗简历草稿](../gmail-resume-preparation-2026-10-17/issues/08-source-bound-fact-findings.md)，采用 `preparation-policy/v1.0`。

准备模式从已采用的完整 JD 分析选材，默认生成英文草稿。明确其他简历语言要求先显示原句并暂停。最终内容先写入独立 `draft.json`，绑定实际 JD、完整资料快照、分析、生成配置与本次准备输入；无 PDF 也能重新读取和审阅。

页面逐来源显示原文／改写、责任归属、范围边界和数字／日期／技术词新增、遗漏。机械提示不代替语义审核。空选材、无合格个人来源或空模型内容停在材料不足，不回退为 JD 关键词编造经历。

显式草稿审阅绑定版本、精确字节与当前输入，并追加审阅历史。输入、资格更正或重新生成使当前审阅失效，旧版本与历史保留；晚返回不能重新采用。草稿审阅不确认 PDF，也不授权投递。可信 PDF／导出重试由后继票单独持有，旧申请模式 PDF 分支保留。

- [独立审查与修复](review.json)
- [本票源码指纹](source-manifest.json)、[领取前基线](baseline)、[本票变更](owned-changes.diff)
- [保留的旧测试基线](preserved-baseline.json)
- [首轮非验收日志](offline.log)、[最后语言修复前的针对性回归](focused.log)
- [最终验证汇总](verification.json)：最终完整离线 **2353 passed / 208 deselected**；[最终针对性回归](focused-final.log) **157 passed / 2 deselected**（含在完整离线内）；[浏览器兼容](browser-compatibility.log) **26 passed**，最后语言修复后的[受影响草稿复验](browser-final-affected.log) **4 passed**（前26项子集，不是新增4个不同场景）。Ruff、238文件格式、JavaScript语法、diff及链接检查通过。

本票已回写关闭，父地图已更新，后继票不自动领取。最终15项源码指纹一致。
`offline.log`／`offline.xml` 是最后语言修复前启动的首轮记录，曾因父子进程加载引擎版本不一致而有1项失败，不作为验收。
[版本差异说明与单项复验](loaded-version-diagnosis.json)保留该失败；[最终全套](offline-final.log)在冻结版本的新进程运行并全部通过，版本保护未放宽。浏览器26项在最后仅语言规则修复前完成，最终4项受影响路径已补验，源版本关系详见汇总。

真实邮箱、模型、岗位页面、App、ATS、上传／Submit、旧申请恢复及安装版替换均未执行。所有资料、模型、导出与浏览器路径只使用隔离合成夹具。没有暂存、提交或远端写入；真实申请继续暂停。
