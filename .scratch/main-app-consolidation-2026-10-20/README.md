# 统一主安装版 — 2026-10-20

用户明确要求把修复接入主安装版、打开设置由本人授权，并避免多个 App 重复授权。本次已完成部署，不代表真实申请恢复或剩余票据整体验收。

当前唯一本机安装入口为 `/Users/zhdeng/Applications/TomorrowStar.app`，bundle ID `dev.tomorrowstar.desktop`。使用原主包 Info.plist 和已验证 PDF 候选全部功能资源，仅重新签名外层。原生代码签名与 Info.plist 是相对候选的仅有差异；manifest、引擎及 helpers 保持候选原字节。并非把当前 checkout 所有未提交改动打包。

## 验证

- 既有整包隔离验收通过，含实际系统 Chrome PDF、运行时、两个入口、模式、回读与 EOF 退出；见 `package-acceptance.json`。
- 安装路径上的连续三次 LaunchServices 原生冷启动与 PDF 导出通过，墙钟分别为 11.201、13.306、3.929 秒。每次单次导出、PDF 一页及文本正确、权限 0600、自有 Chrome/原生/后端退出、临时 profile 清理、无模型调用/真实 ATS/上传/Submit；见 `cold-start-01.json` 至 `cold-start-03.json`。
- 普通 `--synthetic-preparation` 窗口实际打开并呈现材料准备页。实际主 bundle/path 与 nonce 桥绑定，controller source/UI 匹配，package loaded_mapping=verified；无任务、worker 禁用且未创建 worker 目录。正常 Quit 后两个自有 PID 均退出。回执 `ordinary-readiness.json`、`ordinary-flow.json`。
- 普通窗口启动样本过期后为 unknown，不是获权检查或三身份交接通过。权限相关验收仍需用户授权后的新实例检查。
- 安装清单、strict/deep 签名和真实 portal 配置前后哈希再次核验通过。

## 回退与收敛

原主 App 备份为 `rollback-main-before.tar`，归档成员原字节、模式和符号链接逐项验证；记录 `rollback-check.json`。Applications 中 27 个未运行的测试 App／旧备份（含隐藏项）已移至 `~/Library/Application Support/TomorrowStar/retired-builds/2026-10-20-main-consolidation/`，改用 `.bundle-backup` 扩展，逐项验证字节、模式、符号链接不变。没有删除内容。原路径与恢复路径只存私有 `retired-apps-private.json`；Applications 当前仅余主 App。历史回执保持原样，其原安装路径现已归档。

## 权限与边界

系统设置已打开到 Privacy & Security → Screen & System Audio Recording，并选中 TomorrowStar.app；Device Control and Data Access 中主 App 也已定位。两个旧 UI 开关显示 on 不证明更新后实际宿主获权。由用户对更新后的主 App 重新切换开关和完成系统认证，本会话未改开关或 TCC。

本地没有有效代码签名身份，当前 ad-hoc designated requirement 绑定 cdhash。因此单一固定 bundle ID/路径可避免多 App 分别授权，但不能保证未来二进制更新永不需要重授。后续遵守 CONVENTIONS.md：仅部署主 App、先完成签名再授权、回退副本不作为额外已安装 App。

旧材料和真实配置保持；新的普通 PDF renderer 配置不自动替换旧材料、不自动重导出或重新确认。26 号票原完整受限沙箱服务拒绝、28 号票剩余获权及交接矩阵仍未通过，真实申请持续暂停。

## 验收脚本更正

初始 staging 校验误要求 CodeResources 必须变化，实际外层签名变更位于 Mach-O 嵌入签名；改为检查允许且必要的身份/签名差异，未修改功能包。归档末尾检查遇到无关 App 的坏 plist，限定 TomorrowStar 路径后完成只余主 App 的回读；27 份移动此前已逐项验证并记录。这两项是验收脚本问题，不记作产品失败。
