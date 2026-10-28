# 安装版 Chrome/PDF 合成验收 — 2026-10-19

已将 LaunchServices 注册预检及失败诊断接入独立安装版，并完成整包验收和连续三次真实原生冷启动、PDF 导出。真实申请保持暂停。原主 App 和连接配置保留。

## 安装与输入绑定

安装路径：`/Users/zhdeng/Applications/TomorrowStar Chrome PDF Verified.app`。独立 bundle ID：`dev.tomorrowstar.chrome-pdf-verified`，ad-hoc 签名且 strict/deep 校验通过。原 `TomorrowStar.app` 未替换。

以原安装版对应的 `build/material25-generated-project-source` 为基线，87 个核心 engine 文件逐项匹配；隔离副本 `build/chrome-native-validation-source` 仅覆盖 9 个明确文件。[输入绑定](source-binding.json)保留文件与哈希。构建产物经整包验证后原样安装，安装清单包含 1462 项、约 328 MB。[安装清单](installed-bundle-inventory.json)。

新增固定 `--pdf-export-check <gui-host-marker>` 诊断入口，复用无窗口原生委托，运行包内 Python、校验自身 manifest 与原生责任链，再执行同包生产 `application_resume.export_pdf`。只使用固定合成 HTML 和新的私有诊断目录，不读取真实申请配置。注册预检明确拒绝时停止，保留阶段和错误，不自动切换宿主或重试。

## 整包和安装后验收

[整包报告](package-acceptance.json)及[日志](package-verify.log)通过：签名、含空格路径重定位、包内 Python/后端/worker 入口、实际系统 Chrome PDF、合成流程、只读 handoff 和正常退出。真实 ATS 提交为零；报告内 submitted/confirmed 仅合成本地状态。

三次从已安装 App 经 LaunchServices 启动实际 NSApp，每次新 marker、新诊断根和新浏览器 profile；均在 40 秒单次观察上限内结束。验收依据是结果回执、实际 PDF、OS 进程责任链和退出核对，不以 `open` 返回零作为成功。

| 次数 | 原生 PID | 包内 Python PID | Chrome PID | 耗时 | 结果 |
|---|---:|---:|---:|---:|---|
| [1](cold-start-01.json) | 64661 | 64723 | 64773 | 6.449 s | 通过 |
| [2](cold-start-02.json) | 65093 | 65096 | 65134 | 7.677 s | 通过 |
| [3](cold-start-03.json) | 65575 | 65584 | 65622 | 3.757 s | 通过 |

三次 build manifest 均一致；包内 helper/engine 哈希匹配，Python 与 Chrome 的 OS responsible PID 均指向本次原生 App。每次实际导出一次，PDF 一页、正文逐项核对、权限 0600。原生无窗口、不激活、无权限提示；自有原生/Python/Chrome 退出，临时 profile 回收。可查看 [第 1 份 PDF](cold-start-01.pdf)、[第 2 份 PDF](cold-start-02.pdf)、[第 3 份 PDF](cold-start-03.pdf)。

这里使用包内导出器和外部 `/Applications/Google Chrome.app` 渲染，浏览器没有打入包。[最终回读](installed-final-readback-corrected.json)纠正旧回读文件的 renderer 用语，原始文件保留。

## 失败路径及回归

[独立故障副本结果](native-denial-fixture.json)：固定合成注入注册拒绝，经实际原生入口得到 `registration_preflight` / `macos_chrome_registration_denied`，导出尝试零、Chrome 启动零、PDF 零，原生/Python 正常退出。该副本单独签名，候选安装包未改；临时副本已回收。这是固定注入，不能冒称实际 OS 拒绝、原 SIGABRT 或主界面错误提示验收。

- 原生路由 RED：4 失败 / 18 通过；[修复后相关回归](focused-green.log)：48 通过。
- 隔离冻结源码[完整默认离线套件](offline.log)：3505 通过，305 按默认标记排除，640.25 秒，退出 0。未放开 live 标记。[结构结果](offline-result.json)。
- 运行前后 493 个文件哈希一致：[运行前](source-before.json)、[运行后](source-after-full.json)。之后仅同步一个 AST 等价的测试格式修正，生产输入不变：[等价证明](test-format-equivalence.json)、[最终清单](source-final.json)。受影响模块重跑：[2 通过](post-format-tests.log)。无需把测试格式修正冒称原完整套件的原始字节。
- 当前 checkout Ruff/格式通过（349 文件），隔离源码 Ruff/格式通过（309 文件），`git diff --check` 通过。Swift 编译随[构建](build.log)通过。

初次误把 Swift 文件传给 Ruff，以及一次收尾命令使用错误工作目录，均为验证调用错误，已纠正；不算产品失败，也未省略任何后续检查。

## 保留边界与票据

[原安装版最终校验](original-app-final-verification.json)通过：原 87 个 engine 和原 helper 哈希、签名、主程序、Info/manifest 及连接配置保持。没有操作真实页面/附件/worker，没有模型调用、Prism 编译、上传、提交或真实申请。没有提交或推送代码。

[26 号票](../single-job-application-flow-2026-10-16/issues/26-native-chrome-startup-crash.md)更新安装包三次冷启动与整包/完整离线验收。票保持 open 和原执行者：历史两 PID 的直接 argv 缺口、原完整受限沙箱的同条件 RED→GREEN、实际同类失败在主界面的准确停止提示仍未完成。当前安装版成功运行在获准的原生 LaunchServices 宿主；此前受控服务实验支持 LaunchServices 拒绝机制，不代表修复工具的原完整沙箱策略。
