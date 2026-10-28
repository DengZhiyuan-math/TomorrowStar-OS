# 安装版合成准备验收

2026-10-18 完成。[规范验证记录](verification.json)区分源码、打包、安装窗口、冷启动、renderer和私人状态保全。真实申请保持暂停；真实推荐和真实简历质量仍须用户参与后继票。

最终候选为 `preparation-candidate-7b299a861113762f4ba5ca5317cea76a35f89360467e90ff572e11c27dcbff1b`，238个公共文件；[严格清单及源码核验](final-run/final-freeze-verify.log)通过。独立安装到 `/Users/zhdeng/Applications/TomorrowStar Preparation Verified.app`，bundle ID为 `dev.tomorrowstar.desktop.preparation-acceptance-v2-20261017`。原 TomorrowStar 与 Page Recovery App 未替换。

| 验收范围 | 结果与证据 |
| --- | --- |
| 完整默认离线 | [2516 passed / 221 deselected](final-run/offline-suite.log) |
| 本地浏览器兼容 | [41 passed / 72 deselected](final-run/browser-suite.log)；独立合成、无账号 |
| 静态检查 | Ruff及258文件格式、JS语法、diff通过 |
| 打包与安装 | [签名前后身份](final-run/package-identity.json)、[安装回读](final-run/installed-package.json)；75引擎文件与候选一致，运行后deep/strict签名仍有效 |
| 实际加载 | [初次进程](final-run/loaded-processes-1.txt)、[重开进程](final-run/loaded-processes-2.txt)、[运行代码与UI](final-run/installed-runtime-identity.json)；4个HTTP静态资源与包内一致 |
| 原生完整旅程 | 更新固定推荐及完整JD→选岗→保存暂停批次→分析与英文草稿→暂停和来源审阅→明确继续→导出→预览和确认具体PDF→等待申请记录 |
| 冷启动恢复 | [任务、整个批次及61文件完全一致](final-run/cold-start-verification.json)；会话改变、代码和UI不变，终点事件仅1条，未自动重跑或启动worker |
| 实际renderer | [一页A4检查](final-run/pdf/renderer-verification.json)、[逐页图](final-run/pdf/page-1.png)、[安装窗口预览](final-run/native-pdf-preview.png)；同一具体PDF哈希绑定任务 |
| 退出与保全 | [最终退出](final-run/quit-2.json)无候选进程、端口关闭、保存文件不变；[两原App及九项私人目录元数据](final-run/preservation-after.json)均保持一致 |

原生窗口通过 Cua 操作；HTTP仅用于读取验收状态和资源。邮箱、JD和模型均固定合成替身，实际PDF沿用当前模板及系统Chrome renderer。未调用真实邮箱、真实模型或真实岗位源，未读取私人记录正文，未操作原页面或附件，未上传、填写或Submit。确认合成材料不代表用户接受真实简历质量。最小合成资料没有教育记录，当前模板保留空Education标题；本轮未改模板。

## 发现与修复

第一次安装旅程发现：已确认材料在退出和重开时重复写入 `waiting_application_record` 事件与epoch。原[失败证据](confirmed-cold-start-verification.json)保留。修复对该终点及 `needs_recheck` 的状态和原因作幂等判断；控制不一致时仍执行纠正。新增4种生命周期回归，[独立审查4项](final-run/independent-endpoint-review.log)及相关50项通过；最终候选完整安装旅程重新执行，61文件、整个批次及单条终点事件均验证稳定。

首次构建命令未带 `-B`，在首个源码快照中产生6个缓存文件；严格核验正确拒绝额外目录。[事件和恢复记录](snapshot-build-cache-incident.json)保留原失败，未覆盖旧快照。最终构建使用 `python -I -B`，构建后与运行后严格核验均通过。首次签名前后的程序哈希也[分别记录](final-package-identity.json)；最终包直接使用明确标注相位的字段。

## 保留与重开

验收结束后候选已退出，合成目录 `/private/tmp/tomorrowstar-installed-preparation-v2-20261017` 保留。需要核对同一合成进度时，必须明确指定合成参数：

```sh
/usr/bin/open -n -a '/Users/zhdeng/Applications/TomorrowStar Preparation Verified.app' \
  --args --synthetic-preparation /private/tmp/tomorrowstar-installed-preparation-v2-20261017
```

默认启动仍使用普通资料连接，因此合成验收不能省略参数。回退只需退出独立候选，使用未替换的原App；无需迁移或回滚私人数据，不恢复旧任务。首个Preparation Candidate安装及失败证据保留为前身，不作为最终接受版本。历史原生故障调查与其他地图不因本次合成通过关闭。
