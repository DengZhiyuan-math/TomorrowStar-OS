# 单岗解释性展示验证

对应[查看单岗的解释性分级](../gmail-resume-preparation-2026-10-17/issues/06-grading-projection.md)。

按 `preparation-policy/v1.0` 在已有完整 JD 列表与任务详情展示匹配分、资格结论、当前进度和具体理由，无 A/B 等级或新分档。匹配沿用 `documentary-match/v1`。人工调序不改分数、来源或事实说明。

未知／冲突的必需资格与不可用分析阻止本岗简历生成。资格更正使已完成或运行中的旧材料失效。输入变更保留历史；信息库／政策同步可保留仍适用的文档匹配分析，事实说明需绑定当前输入。其他岗位的解释不因单岗读取失败消失。

信息库只读，不启动填写 worker，不初始化／迁移资料，不读取旧 run／owner。自动资格核对仅支持已审核的单一法语／德语 CEFR 条件；其他硬条件保留事实说明。自由格式偏好不被推断为新的硬限制。

- [独立审查与修复](review.json)
- [本票源码指纹](source-manifest.json)、[领取前基线](baseline)、[本票变更](owned-changes.diff)
- [完整离线日志](offline-tests.log)、[针对性回归](focused.log)、[合成浏览器](browser.log)
- [最终验证汇总](verification.json)：完整离线 **2294 passed / 204 deselected**；针对性 **110 passed**（包含在完整离线内）；合成浏览器 **22 passed**。Ruff 检查、233 文件格式、JavaScript 语法和 diff 检查通过。17 项源码指纹最终一致。

真实邮箱读取／写入、模型调用、岗位页面获取、ATS、上传和 Submit 均未执行。真实 App 未启动，安装版未替换，真实申请继续暂停。没有暂存、提交或远端写入。本票已回写关闭，后继票不在本轮自动领取。
