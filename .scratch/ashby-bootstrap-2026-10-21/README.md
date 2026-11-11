# Ashby 公开初始化源码切片 — 2026-10-21

范围为[原票 33](../single-job-application-flow-2026-10-16/issues/33-ashby-public-bootstrap-review.md)的当前替代范围。复用原 Runner、原页和既有 Ashby 草稿适配器。安装更新与真实申请继续暂停。

复用已保留的官方公开客户端 AST 确定两个公开根字段与变量：岗位读取 `jobPosting` 绑定当前组织及岗位；组织读取 `organizationFromHostedJobsPageName` 绑定当前组织，应用页 `searchContext` 可省略、为 null 或为 `JobPosting`。官方 AST 原件、来源定位及核对脚本保留在私有证据中；没有新增网络读取，没有复制真实岗位或组织资料。

`ashby_drafts.py` 复用既有有界语法读取，公开查询支持 selection fragment、内联 fragment、根字段别名和 operation 名称变化；不按 Query 字节或名称建立人工批准。仍只接受一个已理解的公开根与直接绑定变量。草稿写入保留原有语义检查。响应使用实际别名，组织响应核对当前 slug；组织读取不能替换岗位表单回读请求。

[Runner 回归](../../tests/test_ashby_bootstrap.py)先通过 `ApplicationRunner.tick()` 与离线 Chromium 重现公开初始化被拒、原表单未出现，再用相同入口验证岗位和组织读取后原表单出现。接收端完全合成，浏览器断网，所有请求截获并核对；没有真实 ATS、安装 App 或既有浏览器操作。

边界回归涵盖改名、fragment、可空上下文、额外或缺失变量、异组织／岗位、mutation、混合最终操作、第二个 query、字面参数替换、变更端点、重定向和组织响应身份。保留的未知 open 不因公开读取而结算。已有受影响离线回归和 Ruff 检查通过。全库结果由本轮主报告记录。

源码回归不证明原历史请求字节相同，不证明真实页面、字段、附件或人工 Submit。原票保持 claimed，原验收与历史勾选不改。

布尔结论见 [verification.json](verification.json)。详细合成日志与执行测量保留在私有临时证据中。
