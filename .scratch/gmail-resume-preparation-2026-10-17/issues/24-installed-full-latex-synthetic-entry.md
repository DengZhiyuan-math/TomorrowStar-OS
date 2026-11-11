# 补齐安装候选的完整 LaTeX 合成旅程入口

Type: task
Label: wayfinder:task
Status: closed
Triage: done
Closure reason: completed
Completion: source-and-synthetic-full-latex-entry-verified
Priority: P1
Interaction: AFK
Assignee: 01a14fd0/root
Created: 2026-10-18
Updated: 2026-10-18
Parent: [交付 Gmail 岗位筛选与专用简历稳定版](../map.md)
Blocked by: [绑定完整源与新 PDF 并单独确认材料](23-confirm-reviewed-latex-pdf.md)

## Question

怎样复用当前完整LaTeX生成、分组审核和严格PDF绑定，使独立安装合成入口能安全运行新链，并核验完整链实际加载身份？

## Observed gap

[当前候选核对](../../current-candidate-journey-2026-10-18/README.md)确认：旧安装旅程使用摘要／HTML路径，现有合成准备夹具没有完整LaTeX底稿，替身模型没有完整生成schema，分组预览及打开Prism仍可能落到真实客户端。不能直接启动它来验证新链，也不能以源码整合测试代替安装验收。

现有加载指纹通过导入摘要间接区分两个新模块的源码版本，但没有直接纳入其实际加载函数。此为身份核验覆盖缺口，不是已观察到错误版本加载或原生故障。

## Acceptance criteria

- [x] 复用现有`--synthetic-preparation`隔离入口，在新合成目录提供独立、Git外的完整LaTeX底稿与明确标注的已确认合成资料；不读取或镜像真实职业资料、邮箱和旧运行。
- [x] 复用现有替身runner，支持完整生成器的`groups`／`limitations`契约，保留旧schema；未知请求失败关闭，禁止退回真实模型或消费宿主凭据。
- [x] 给合成准备路径显式注入隔离Prism打开与编译替身，覆盖两个入口，禁止退回真实`PrismClient`。固定PDF明确标为合成夹具，严格绑定完整源、主文件、输入与回执；不将其当作真实编译或版式质量证据，不重建renderer。
- [x] 使用实际store／flow验证逐组确认、未变继承、完整源与新PDF绑定、每版独立材料确认、改后失效及历史保留；未知结果只核验既有回执，明确重试不重放未知动作。继承现有测试，不重复实现业务规则。
- [x] 完整链两个新模块的实际加载函数、默认值及常量纳入现有加载身份核验；沿用当前指纹机制，以定向回归证明覆盖，不能只比较磁盘文件或导入时源码摘要。
- [x] 验证合成入口退出／重开只恢复进度，不自动生成、打开Prism、编译、确认材料或执行worker。保留默认入口、旧合成入口及原读取限制。
- [x] 以最小源码／合成、HTTP和原生后端回归证明可打包入口安全可用；真实隔离安装、实际加载资源、整链冷重开及分阶段测量仍由[核对当前安装候选的完整材料准备链](19-current-candidate-journey.md)验收。

## Ownership and boundaries

最小范围为`create_synthetic_flow.py`、现有替身runner、原生合成准备装配、Portal的Prism依赖注入及加载指纹和相关定向测试。复用当前构建和冻结脚本；不加依赖、不扩普通资料读取、不开放独立真实Prism配置，不改人审或申请门槛。

先领取再执行，使用既定TDD流程；共享源码须协调，不回退其他工作。仅创建前置不表示实现完成，也不使当前候选整链通过。真实材料确认、模型、Prism、ATS、上传及Submit仍保持原授权边界，真实申请继续暂停。

## Resolution comment

源码与安全合成入口已完成，见[冻结候选与最终验证](../../installed-full-latex-synthetic-entry-2026-10-18/README.md)。实际安装验收与真实材料质量接受仍由后继持有；未构建或替换安装App。

### 2026-10-18 — Claim and execution scope

用户授权开始本票；核对直接前置已closed且未领取后，由`01a14fd0/root`领取。复用已有完整链、确认记录和合成验证，仅补固定完整底稿、替身schema、隔离Prism入口及实际加载身份覆盖。采用TDD；不读真实职业正文／邮箱、不启用真实模型／Prism、不构建或替换真实安装、不恢复申请。隔离原生后端的源码验证与安装整链验收分开。

### 2026-10-18 — Source and synthetic entry completion

固定完整底稿、已确认合成身份和完整生成schema已接通；仅字面复用资料，未知陈述保留待核对。分组预览、正式PDF绑定及配置共享注入的固定PDF客户端，合成打开Prism明确拒绝真实连接。固定PDF只作传输和状态夹具，不证明真实编译或版式；正文、分组及每份材料确认门槛保持。

实际CLI→原生合成后端→HTTP完整链、改组继承、同PDF新版本独立确认、历史源／PDF回读及EOF／SIGTERM重开通过。损坏、缺失、链接PDF及外部项目失败关闭；未知尝试重开后只核验，不重放。完整生成与分组审核的加载函数、默认值及常量已纳入现有身份机制，默认和旧合成入口回归通过。

TDD红绿记录、完整默认离线、定向及独立复核、Ruff和差异检查均通过，并绑定同一冻结源码候选。详细结果与修改前字节私存，公开仅保留审核允许的布尔结论。早期RED曾触发旧打开回调的本机只读连接尝试，未进入编译；失败及披露已保留，不当作安全通过，也不声称本轮全程零真实连接。

本票按源码及合成范围结案；[当前安装候选整链](19-current-candidate-journey.md)保持open／none，直接前置现均已完成，可另行领取。未读真实职业正文／邮箱、未执行真实材料编译、未更新安装或恢复任何申请，原三项HITL及旧领取保持。
