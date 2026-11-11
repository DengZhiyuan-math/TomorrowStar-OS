# 主安装版原生验收续作 — 2026-10-20

已将本轮工程增量接入唯一固定签名主 App。24 的六项工程验收已齐；25 补齐持久诊断和两个实际机制。28、30 仍保留未完成范围。所有原 Status、Assignee 和依赖保持，仅回填有独立证据支持的验收勾选。未恢复真实申请，职业材料问题全部暂缓。

## 本轮结果

| 票 | 已完成 | 仍保留 |
| --- | --- | --- |
| 24 | 同候选双 Chrome/多标签精确原页；新鲜字段/有效性/PNG/非空同一 File；owner、真实 proxy 退出、关闭/替换页和字段/document 漂移拒绝；观察无业务副作用；正常 Quit/重开后原页可读 | 六项技术验收均有支持；原 claimed/领取人保持，供原领取统一结案。真实页未恢复 |
| 25 | 请求→原 intent/attempt/字段/batch/run/Page 的持久诊断与首个 stop request_id；telemetry POST→公开 GET 和真实 input→autosave 两种独立机制；当前主包只读与安装反例通过 | 仅勾 1/2/4/6。3/5/7 未作整项完成；历史真实 P08/P09 仍未唯一归因，真实后继保持 30 之后 11/23 |
| 28 | 当前候选 controller/运行 worker/磁盘包及 loaded mapping 核对；实际 native check；十二个受控否定 proof 的真实 POST 拒绝且业务字节保持；相同实际证明下 prepare 与明确 resume 正例；重开可读但执行仍拒绝 | 配置不等价、精确历史兼容交接、真实进程接管及完整持锁 TOCTOU。生产历史白名单为空，不勾剩余整项 |
| 30 | 固定 integration 枚举及实际主 App 六项填写：姓名、邮箱、combobox、radio、checkbox、date；逐值原页回读，保留既有偏好/note；缺检查点保持 needs_input | 没有 Workable 签名上传接收端/远端 SHA/ready_for_review；26/27/28 原门槛及完整组合仍未完成 |

## 准确的证据分层

- **源码完整默认离线：3744 passed，2 skipped，311 deselected。** [最终日志](full-offline-final.log)。Ruff、格式及 whitespace 检查通过。
- **当前安装包适用回归：129 passed，8 deselected。** 包内 Python 执行，已加载 engine 模块均核对来自主包。四个源码布局专用 case 不适用于安装位置强制 strict 的守卫；另四个浏览器 case 由默认 marker 排除。[选定日志](packaged-regression-selected.log)。原 3 failed/1 error 及逐案解释保留，未放宽安装守卫以使其通过。
- **包验证：** 固定签名、完整清单、加载映射、迁移、独立后端及实际离线 system Chrome PDF 导出通过。这是包验证进程，不冒充原生主宿主。
- **实际主宿主：** 无提示权限探针通过；固定后台诊断运行实际 retained Cua Page 和生产 command handler。普通主窗口另有实际 scoped POST、managed worker、六项字段及双实例证明。合成 WorkerStore 的固定后台病例不冒充普通跨进程 handoff。
- **重开：** 原 worker OS 启动代次、run/Page、字段、答案及 PDF 保留。新控制端只读入口可用；process/compatibility 仍 unknown。fresh 新宿主 check 存在时 resume 仍 409，serial/run/pid/Page/job/受保护字节保持。此状态同时有历史页证据等限制，不宣称唯一隔离了 unknown process 的拒绝原因。

完整默认 suite 的第一次失败为旧 Request 替身缺少 `resource_type`；只修测试并增强不变量断言，产品代码未为替身增加兜底。原日志保留，最终全套已重新通过。测试修正后的最终 source freeze 与实际构建 v2 只有这一测试文件不同，engine 字节相同。

## 原生边界与失败保全

六类故障逐案核对具体 reason，失败回执无 data/screenshot；正例观察不触发页面 getter、事件、DOM mutation 或写请求。P08 的 GET 仅记 permitted/dispatch unknown，浏览器 offline，不代表远端成功。P09 实际 input 事件触发拒绝 POST，同页原输入和同一 File 保留；两组记录经新 WorkerStore 重读。[独立最终审查](identity/native-evidence-review.md)。

权限/nonce/责任链/过期/unknown 的矩阵仅在明确 `--synthetic-browser` 中把实际 native snapshot 降级。没有正向伪造许可、HTTP fault 写入口或系统 TCC 改动。`after-first-read` 未追踪实际锁阶段，UI 也可能读取 snapshot，所以不计完整 TOCTOU。单独 running readiness 虽验证三身份，同时保留 `inputs=state_changed` 和历史 Page，不能写成整个 readiness 全绿。

原工具完整沙箱的四个浏览器用例均停在 Chrome 启动的系统服务权限拒绝，未进入功能断言。[原始失败](observation/browser-regression.log)保持；主 App 成功不关闭 26 的同条件缺口。27 仍缺真实 compiler/attempt 屏障；固定 PDF copier 不代替真实编译。

外层过程采样竞争、错过双标签阶段、心跳/缓存投影比较和归档父目录缺失等 harness 失败均保留原记录并单列后继，不算产品 RED。scope 刷新与字段未知结果也不冒充 GUI 丢失 Cua 回执或长期非空 File 的完整验收。

关于前轮 CLI 归因的更正：逐字比较证明只有 `exec` 的 Python 路径不同，其余行一致；`synthetic_cli_text()` 插入实际 `sys.executable`，所以是生成器解释器差异，不能归为较新 fixture 模块版本。前轮失败原件不改，本轮用实际包内 Python 生成 exact fixture，未放宽验证。

## 收尾与待确认

两个普通窗口正常 Quit；暂停独立 worker 随后按精确 OS 代次与完整命令核对，只清理本轮自有合成进程。登记进程、两个 loopback 端口、profile/socket 均已核对退出/移除。主 App 全树字节/模式/签名和真实连接配置字节保持。

原始截图、字段、路径、PID 和摘要保存在私有持久归档及固定主 App 诊断目录；副本逐字节/模式/链接核对，原历史路径保留。固定签名非 App 候选与原主包回退副本已保全。[公开 Boolean 核验](verification.json)。

本轮没有新增需用户人审或确认领取的请求，未改变任何原领取。25 继续保留 open/none，24 继续保留原 claimed；当前开放数仍为 18，技术验收勾选不能冒充已改票据状态。职业材料事项不列入本轮待办。真实 Gmail、模型、ATS、上传与最终 Submit 均未操作，真实申请继续暂停。
