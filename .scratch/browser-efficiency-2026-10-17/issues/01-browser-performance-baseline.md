# 定位浏览器控制的分段耗时与重复调用

Type: task
Label: wayfinder:task
Status: closed
Priority: P0
Interaction: AFK
Assignee: 01a14a28/root
Created: 2026-10-17
Parent: [交付 DOM 优先的受控浏览器效率改进](../map.md)
Blocked by: 无

## Question

当前慢主要发生在启动、绑定、DOM观察、Cua快照、动作、回读还是异常恢复，哪些有可复用的真实证据？

## Work and reuse

- 复用MeasurementLog、原intent/run/page和现有计量合同，区分机器、排队、用户等待与unknown。
- 先读取已有可用脱敏trace和源码，补最小分段；需要采样时用独立合成页，不动原申请。
- 分别记录冷／暖启动、DOM／Cua、每控件RPC／快照次数、观察payload大小、成功／失败／取消。

## Ownership

按[执行导航](../README.md)所列现有模块及该票涉及的最小测试负责；共享cua_driver.py、application_worker_browser.py、hosted_ats.py或worker_measurement.py时先协调。不得回退其他人的工作，不修改或接管既有私人运行。

## Acceptance criteria

- [x] 基线绑定实际代码／包／配置和控件形态，测试套件耗时不能冒充单岗耗时。
- [x] 源码推断的调用次数与实测墙钟分开；缺数据保持unknown，不先认定截图或模型是唯一瓶颈。
- [x] 输出有证据的优化候选与范围；不新增模型、并发、常驻进程或真实ATS采样。

## Verification and boundaries

遵守[地图](../map.md)、[开发约定](../../../CONVENTIONS.md)和[数据边界](../../../docs/data-boundaries.md)。本轮仅建票、不领取、不跑浏览器；后续仅在实际授权范围执行。人工最终Submit、未知动作停止和原页保留边界不变。

## Resolution comment

2026-10-17：本票完成当前隔离路径的可重复基线、分段失败及优化顺序判定，详见[基线报告](../baseline-report-2026-10-17.md)和[合并工期](../../../research/tomorrowstar-combined-delivery-estimate-2026-10-17.md)。

- 真实ApplicationRunner按生产tick→pump执行5轮，每轮12次verified字段动作，3.775秒中位，固定pump合计约3.06秒、占68.3%–81.8%。较早0.505秒仅tick-only，不是完整循环。
- DOM正式基线77cases、3671spans；生产pump补充5cases、1588spans。5次新profile启动0.282–0.755秒，均关闭所属端点。没有真实ATS／模型／Gmail／上传或ready_for_review声明。
- 真实Cua：批准执行环境权限24.0ms通过，browser_prepare15.02秒unknown；停止未重发。沙盒权限拒绝与该事件分开保留；真实快照／点击仍未知，交[核验原生启动并补齐Cua真实操作基线](11-native-cua-baseline.md)，不冒充已通过。
- 仅基线票关闭，没有实施性能优化。相关默认离线56 passed、12 deselected，Ruff check/format通过；生产执行器未改，完整产品套件／安装／真实网站不在本轮通过范围。
- 真实申请继续保持用户暂停决定。新原生runtime.closed=false保留；只读资源回读无对应新browser进程、socket或SingletonLock，未以此覆盖未知动作。

## Execution claim — 2026-10-17

用户授权先执行隔离合成浏览器性能基线、确定优化顺序并更新两条路线合并工期。01a14a28/root领取本票；仅自有临时浏览器／合成页面，不读Gmail、不调用真实模型、不接管或恢复原申请。历史建图记录保留，以下执行事实另记。

