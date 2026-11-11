# 用户报告开启权限后的实际核验 — 2026-10-20

分别从 LaunchServices 启动独立候选与主安装版的固定 `--permission-check` 入口。两者均为新进程、零窗口、非激活、零权限提示。原生及嵌入探针一致返回辅助功能 false、屏幕录制 false，Python/daemon/proxy 均归属于相应原生宿主。该结果不判断系统设置开关状态或授权失败根因。

- 独立候选：`dev.tomorrowstar.chrome-pdf-verified`，1.900 秒，见 `result.json`。
- 主安装版：`dev.tomorrowstar.desktop`，1.705 秒，见 `main-app/result.json`。
- 两者 manifest 检查前后相同，strict/deep 签名通过。独立候选 1463 项历史清单逐项匹配。
- 两次登记的八个 PID 均经独立 ps 核验退出；未发送 browser_prepare，真实 ATS、上传、Submit 均为零。

权限对这两个实际 App 身份尚未生效。28 号票获权正例及其依赖的普通窗口验收保持阻塞。26 号票原完整受限沙箱的服务拒绝属于另一个尚未证明修复的边界。未改 TCC、安装包或真实配置，真实申请继续暂停。

原始回执另保存在各 result.json 的 diagnostic_root 指定的持久私有目录。这里只记录本次验证；不补签已丢失的历史临时基线，不标记 32 号票整体完成。
