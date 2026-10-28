# finalization-fix 独立审查完成入口

Standards：0 项规范违规，0 项可操作启发式问题。Spec：0 项发现。[完整审查报告](../application-worker-targetclosed-rerun-finalization-review-2026-10-12/README.md)保留两轴独立报告、固定包差异、执行源码和全部探针。固定入口 SHA256 为 `b0473c4e226de2b35b1d94031a82fc4e53a31362167ac8ea50d84f6f3bb7784d`；与封存 subdirs-fix 比较。

| 检查轴 | 结论与验证 |
| --- | --- |
| Standards | 0 规范违规，0 启发式问题；独立新入口 14/14 通过 |
| Spec | 0 发现；独立唯一场景 33/33 新入口通过；新入口 636 代目录描述符全部关闭，cwd 恢复 |
| 既有回归副本 | 280/280 通过；0 failure/error/skipped |
| 实际源包拒绝 | 56/56；未创建受保护目标 |
| 失败原件复读 | 源包 3 份最终化失败见证的外部原件完整，定位有效 |

清理门槛符合请求：最终输入匹配且 result.json 写入、flush、close 完成后才清理。输入异常、不匹配及 result 打开/写入/关闭失败均保留外部原件和有效定位。独立探针还覆盖归档异常、子目录替换、描述符关闭及工作目录恢复。本次只新增审查证据，没有修复入口代码或新增浏览器、ATS、模型调用。生产恢复未验证。

初次核对的 3637 个公共哈希全部不变。末尾核对为 3628 个不变、9 个未封存工作区文件变化。14 个旧封存包的哈希、文件集、完整树及链接目标不变；私有原字节/元数据与私有诊断包不变；04、06 均保持 closed。9 个路径及前后公共哈希见 [最新复核](review-check-final.json) 的 preservation。本审查未写入这些路径，未确定变化发起者。旧原生归档的字节、事实对应、ZIP CRC 和外部副本有效；它们的当前输入绑定为 false，不能用于验证变化后的工作区。固定入口的审查结论不扩展到该工作区。

原审查目录的第一次封存脚本按文件名排除了 manifest，漏计嵌套的 `spec/evidence-hashes.json`。原文件集检查失败，退出码为 1。[失败记录](original-failure.json)、[stderr](original-postseal.stderr.log)和原清单保持原样，没有将失败改记为通过。[完整清单](complete-review-seal.json)补充该嵌套 manifest，并单独核对原清单 SHA256；共覆盖原目录 88 个文件。原审查目录未作后续编辑。[修正复核器](postseal_check.py)复用原复核逻辑，改用该完整清单，并继续报告未封存输入漂移。

本补充证据也由 `evidence-hashes.json` 封存。包外完成回执为 [封存后回执](../application-worker-targetclosed-rerun-finalization-review-seal-check-postseal-2026-10-12.json)。回执重新核对本补充证据、原审查目录、源修复包、旧包、私有聚合结果和 closed 状态。所有失败记录均保留。
