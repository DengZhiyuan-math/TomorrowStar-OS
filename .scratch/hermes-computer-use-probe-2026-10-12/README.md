# Hermes computer-use 环境检查 — 2026-10-12

本轮核对已安装的 Hermes 和 CuaDriver。所有实际页面都是本地合成页面；未修改既有 profile、gateway、认证或用户日常浏览器。

- [环境身份](environment.json)：Hermes head 和包装器输入哈希、CuaDriver 0.21.0。
- [健康检查](doctor.json)：辅助功能、录屏与 AX 已可用；专用直接捕获检查 skipped。
- [隔离浏览器创建](action-05.json)：Cua 创建新进程，未复制或修改已有 profile。
- [最后状态请求](action-07.json)：socket connection refused；动作结果 unknown，没有重放。

用户随后要求直接接入 CuaDriver。后续[原生 MCP 验证](../cua-direct-probe-2026-10-12/README.md)不依赖 Hermes，已经完成合成页面交互和同浏览器 Playwright 请求拦截。
本报告保留 Hermes 路径的原观察，不将它们改记为通过，也不把未知 socket 故障归因为缺少 TCC 权限。
既有 Chrome PID 请求被自动审批拒绝后未执行；后续使用全新测试进程与 driver-owned profile，没有改变 existing-profile 授权。
