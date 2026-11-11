# 自动填表接入：三轮合成测试

日期：2026-10-09。两轮完整填写通过；一轮缺失答案按预期拦截。
三轮最终操作均未触发。未使用真实个人资料，未向招聘网站提交申请。

## 测试结果

| 轮次 | 场景 | 浏览器结果 | 判定与证据 |
| --- | --- | --- | --- |
| 1 | Lever 完整合成资料 | 填写必填字段，上传合成 PDF，进入 Review application | [9/9 检查通过](round-1-lever.json)；[复核页截图](round-1-lever-review.jpg) |
| 2 | Greenhouse 完整合成资料 | 填写必填字段，上传合成 PDF，进入 Review application | [9/9 检查通过](round-2-greenhouse.json)；[复核页截图](round-2-greenhouse-review.jpg) |
| 3 | Lever 缺失工作授权、签证支持、薪资答案 | 三项必填提示，停留在填写页；最终按钮未出现；拒绝记录 reviewed | [预期拦截通过](round-3-missing-answers.json)；[拦截截图](round-3-missing-answers.jpg) |

完整回放的九项检查覆盖必填字段、附件存在、附件文件名、进入复核页、
started → reviewed 记录、无申请 completed 记录、关联会话、会话不保存答案值、
最终操作未触发。第一轮重复记录 reviewed 返回 `changed: false`，验证了幂等性。

第三轮保留[完整填写 oracle 的原始 failed 报告](round-3-oracle-raw-failed.json)。
该报告准确列出三个缺失字段，并报告未复核、生命周期未完成、会话未关联到
reviewed 记录。`session-present` 要求关联到已复核记录；第三轮实际存在
started 会话，因此此项失败不是会话丢失。检查脚本最初将此项误列为应通过；
核对 oracle 定义后修正了检查预期，没有改变浏览器、会话或原始结果。
第三轮仅证明缺失必填答案时的页面拦截和 reviewed 状态守卫。
它不单独证明模型能识别真实网站上的所有未知问题。

## 同轮回归

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 本地交接及 HTTP 契约 | 72 passed，55.64 秒 | [测试日志](contracts-rerun.txt) |
| 插件异常路径 | 9 passed，2.205 秒 | [测试日志](negative-rerun.txt) |
| 新 App 独立运行验收 | 通过 | [验收结果](app-acceptance.json) |

异常路径覆盖错误路由 token、损坏及未来版本数据、非法复核状态、路径穿越、
错误附件文件名、缺失复核事件、错误完成记录、旧版本策略和答案范围不匹配。
App 验收覆盖重定位、内置运行时、文档读取前后签名、只读任务交接、Host/CSRF、
状态操作和父进程退出后的停止。现有安装版 App 未替换。

本轮没有重跑之前的 650 项系统测试或 308 项插件完整测试。
之前中断的 [Lever failed 记录](../lever-interrupted.json) 保持原样。

## 耗时与范围

第一轮文件选择、上传及回读的组合 CUA 调用耗时 545.88 秒。
第二轮拆分后，选择器调用为 502 ms，`setFiles` 调用为 17,632 ms。
第三轮 `setFiles` 调用为 7,731 ms。调用耗时包含浏览器工具处理；
这些数值不是招聘网站响应时间，不能据此认定卡顿已修复。

这些是本地 loopback 夹具上的监督式浏览器回放。
交接接口、插件状态守卫和浏览器操作分别验证；未自动启动新的 Codex 对话。
尚未验证真实 ATS 的登录、CAPTCHA、页面变化、真实资料传输或投递回执。
样本不足以评估真实投递成功率或长期无人值守可靠性。

## 输入与清理

插件版本 `1.1.0`，上游 revision
`370204c58b1137d08c5a7e7449538ae6447be0b9`。
[输入记录](inputs.json)与[结束核对](end-state.json)确认相关代码和测试哈希未变化，
已安装的两份 Skill、存储 helper、QA coordinator 与固定上游版本一致。

每轮先 resolve 路由，再通过带显式 `--root` 的 helper 使用隔离存储。
没有初始化正常申请者存储。仅在浏览器实际进入复核页后记录 reviewed。
第三轮守卫返回 `replay review event not observed`，退出码为 2。
oracle evaluate 之后使用上游 cleanup，三轮报告均保留；合成运行资料已清理，
三个本地监听端口均已停止，浏览器测试页已关闭。
cleanup 的 `state: completed` 表示测试评估完成，不表示申请已提交。

本地回归命令：

```sh
uv --cache-dir /private/tmp/tomorrowstar-uv-cache run --locked \
  python scripts/run_pytest.py \
  tests/test_application_automation.py tests/test_career_portal_http.py -q
uv --cache-dir /private/tmp/tomorrowstar-uv-cache run --locked \
  python macos/verify.py \
  --app build/macos/application-automation/TomorrowStar.app \
  --report build/macos/application-automation/acceptance-round-2.json
```

浏览器回放复用 [Job Apply 插件](https://github.com/neonwatty/job-apply-plugin)
的 prepare、resolve、started、reviewed、evaluate 和 cleanup 命令。
执行时按[接入说明](../../../../docs/application-automation.md)保持人工最终提交边界。
