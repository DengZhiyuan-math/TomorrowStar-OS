# 30/34：G1/G2最小合成入口

父任务完整默认回归已完成：4608 passed、2 skipped、561 deselected，812项输入不变。父任务已完成冻结交接并释放共享文件。本轮在其后继上实施，不覆盖父候选和失败历史：[父任务收据](../ticket34-30-integration-preparation-2026-10-21/full-v1-run.json)。

## 已接入的最小入口

| 入口 | 实现与已验证行为 | 边界 |
| --- | --- | --- |
| G1 `create_synthetic_flow.py --mail ROOT` / Native、server `--synthetic-mail ROOT` | 固定隔离目录；Native只保存标签并重新读取当前配置，保持目录不变；两封推荐分两页；LinkedIn固定来源重定向到预置Lever记录；复用Intake持久化、Pipeline与模拟worker；标签未配/坏值仍收录；第二封归档模拟成功但回包丢失，重开后inspect核对，不重复归档；缺重要事实时停当前岗，继续capture不推进下一岗 | 无真实Gmail、模型、Prism、ATS或CUA；固定预览PDF不是实际编译。当前固定岗位故意缺申请国家，等待处不宣称完成填写或上传 |
| G2 `create_synthetic_flow.py --browser ashby-bootstrap ROOT` / 既有 `--synthetic-browser ROOT` | 固定Ashby原页及posting、organization两项公开JSON均经原Runner guard；同一来源固定响应，不放开外部网络；表单出现后停在缺失答案；旧dom/manual/unknown/integration/integration-upload保留 | headless Chromium仅作源码行为检查，零填写/上传/Submit；不代替安装版或真实网站验收 |

未增加业务状态库、审批步骤或重复版本审核。旧合成模式仍禁用真实Gmail和目录修改。普通生产主流程与请求guard不改。

## 检查与证据

- [原生入口检查](native/)：RED→GREEN；最终125 passed、37 deselected；Swift typecheck与Ruff通过。只编译命令行harness/类型检查，没有构建或启动App。
- [G2检查](ashby/README.md)：默认相关37 passed；合成浏览器6 passed。包含新入口与旧场景，结果重叠不相加。
- G1历史失败保留：`mail-generator-red.txt` 缺少入口；`mail-adapter-red.txt` 缺少adapter；`mail-adapter-green.txt` 仍失败（固定推荐错用Lever链接，被既有LinkedIn/Indeed收录规则过滤），修正来源链接及固定重定向后的 `mail-adapter-green-v2.txt` 通过；`mail-backend-red.txt` 缺少后端入口；`mail-backend-green.txt` 因模拟worker使用了CUA专用click route而失败，`mail-backend-green-v2.txt` 通过；`mail-queue-first.txt` 因预置JD为空而冲突，固定记录对齐后的 `mail-queue-green.txt` 通过。失败文件名不表示通过。没有为样例接线问题放松生产规则或新增审核点。
- 合并后的受影响检查及完整默认回归记录在本目录独立日志和 `*-run.json`。父结果不覆盖本轮新增源码。受影响434 passed、9 deselected；隔离浏览器19 passed、77 deselected，均814项输入无变化。完整默认4632 passed、2 skipped、562 deselected，936.66s；814项输入前后不变。两项skip为既有显式opt-in PDF性能/渲染benchmark，不宣称性能通过。
- 只读整合复核未发现可触发的不一致；检查了固定目录、标签保存、全部模拟adapter显式注入、无真实传输fallback及旧模式行为。
- [开始源码指纹](source-before.json)；本轮复用父任务检查脚本生成完整测试输入前后指纹，不以HEAD代替dirty/untracked输入。

源码候选：425项，`preparation-candidate-36f4e3ca0017eba829b90172b148984e7eb0a4b50a6510905b57f22424097868`。[候选清单](source-candidate-v1/manifest.json)、[相对父候选的9文件差异](source-delta.json)、[源码核对](candidate-verify.json)、[未来入口命令](commands.md)。它不是安装包或独立完整测试checkout。

## 当前未执行事项

App更新和真实申请继续暂停。未构建、安装、启动App；未读写真实配置、邮箱或申请网站。唯一主App和最终手工Submit规则不变。30/34继续claimed，不改Assignee、依赖和历史验收勾选；源码入口补齐不等于安装/真实体验结案。

未来暂停解除且唯一主App更新到本候选后，才使用生成器产生的新ROOT启动相应现有主App入口。本记录不提供现在运行App的许可。
