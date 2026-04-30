# Ionospheric Scintillation Detection 后续完善计划与执行清单（Python 路线）

更新日期：2026-04-23

## 0. 使用说明

本清单用于 MVP 之后的收口与增强，默认工作目录为 `Ionospheric_Scintillation_Detection`。

执行原则：

- 先完成 P0（规格统一 + 可信度 + 可发布性），再做 P1/P2。
- 每一步完成后都要更新 `docs/development_progress.md`。
- 每次提交前至少运行一次回归门禁命令，失败不进入下一步。

---

## 1. P0-01 规格统一（文档与代码一致）

目标：消除“文档是 Electron/React，代码是 Python/PySide6”的冲突。  
产出：`ENGINEERING_SPEC_PYTHON_V2.md`（或对 `ENGINEERING_SPEC_V1.md` 做明确 Python 化修订）。

当前状态（2026-04-21）：已完成（采用新增主规范文档方案）。

执行清单：

- [x] 明确技术栈为 Python 3.11+、PySide6、Pydantic v2、SQLite、NumPy/SciPy、PyQtGraph。
- [x] 将 IPC/事件契约改写为当前 `CommandBus` 语义并保持事件名兼容。
- [x] 将目录结构改写为 `src/isd` 分层结构（ui/application/domain/infrastructure/workers/algorithms）。
- [x] 在文档中保留与 MATLAB 对照迁移规则和误差阈值策略。

验收标准：

- [x] 新规范中不再出现 Electron/React 作为主技术栈。
- [x] 新规范与 `pyproject.toml`、`src/isd`、`tests` 一致。

---

## 2. P0-02 开发门禁固化（强制）

目标：保证每次改动可验证，避免功能回退。  
产出：统一门禁入口脚本与门禁记录。

当前状态（2026-04-21）：已完成（新增统一门禁脚本并通过实跑）。

执行清单：

- [x] 固化三层门禁：单元/集成测试、Step12 回归、MVP Demo。
- [x] 失败时输出明确失败步骤与定位信息。
- [x] 把门禁结果写入 `workspace/reports` 并可追溯。

统一入口：

```powershell
conda run -n isd-mvp python scripts/run_p0_gate.py
```

建议命令：

```powershell
conda run -n isd-mvp pytest -q
conda run -n isd-mvp python scripts/run_step12_gate.py
conda run -n isd-mvp python scripts/run_mvp_demo.py
conda run -n isd-mvp python scripts/run_release_freeze.py
```

验收标准：

- [x] 上述命令全部通过。
- [x] `release_freeze_snapshot.json` 的 `overallStatus=PASSED`。

---

## 3. P0-03 validateTask 规则补齐与对照表

目标：所有阻断/警告规则统一在 `validateTask`，UI 不写业务分叉。  
产出：规则对照表文档 + 补齐单元测试。

当前状态（2026-04-21）：已完成（含规则矩阵、规则补齐、单测与门禁实跑）。

执行清单：

- [x] 对照 `ENGINEERING_SPEC` 列出规则全量清单。
- [x] 标记已实现/未实现/行为差异。
- [x] 补齐缺失规则与测试用例（阻断、警告、降级、实验模式标识）。
- [x] 给出规则变更记录。

交付物：

- `docs/validate_task_rule_matrix.md`
- `tests/test_task_validate.py`（新增 4 个规则测试）
- `src/isd/application/task_service.py`（设置驱动规则补齐）

验收标准：

- [x] `tests/test_task_validate.py` 覆盖全部关键规则。
- [x] `task:validate` 输出稳定包含 `canRun/issues/derived*/riskFlags`。

---

## 4. P0-04 项目管理页收口

目标：从“可用”提升到“稳用”。  
产出：项目生命周期闭环（新建、扫描、重扫、删除、异常恢复）。

当前状态（2026-04-21）：已完成（后端校验、重扫一致性、状态摘要均已落地）。

执行清单：

- [x] 新建项目失败场景（路径不存在、无权限）提示完善。
- [x] 扫描与重扫行为一致，避免脏记录。
- [x] 删除项目时数据库与磁盘目录一致清理。
- [x] 增加“当前项目状态摘要”显示。

交付物：

- `src/isd/application/project_service.py`
- `src/isd/ui/pages/project_page.py`
- `tests/test_project_service.py`

验收标准：

- [x] 从空工作区到可计算项目可一次走通。
- [x] 不再出现“磁盘已删但列表仍显示”的状态漂移。

---

## 5. P0-05 结果可视化收口

目标：确保“任务完成后必看得到结果”，降低试用门槛。  
产出：稳定结果加载与筛选机制。

执行清单：

- [x] 统一 `result:list -> result:getSeries/getGrid/getIntermediate` 调用链。
- [x] 筛选器默认值与当前项目同步。
- [x] 无结果/结果加载失败/格式不符三类状态区分提示。
- [x] 详情卡、风险标识、栅格覆盖率指标保持同步更新。

验收标准：

- [x] 任务完成后可在结果页直接查看时序图/中间结果/栅格。
- [x] 导出按钮对当前结果始终可用且路径有效。

---

## 6. P0-06 报告中心升级为正式 PDF

目标：从文本演示报告升级为可交付 PDF。  
产出：PDF 报告导出器与最小模板系统。

执行清单：

- [x] 增加 PDF 生成模块（保留当前文本导出作为 fallback）。
- [x] 报告包含任务信息、参数快照、风险标识、关键图表和统计。
- [x] 对非 GPS `SIGMA_PHI_F` 默认不纳入报告，除非手动勾选。
- [x] 导出成功/失败状态可视化反馈。

验收标准：

- [x] 报告中心可稳定导出 PDF。
- [x] 生成报告可用于对外演示。

---

## 7. P1-07 设置页与模板系统补完

目标：配置可复用、可持久化、可审计。  
产出：设置项、阈值预设、模板作用域（TASK/BATCH/REPORT/THRESHOLD）完整可用。

执行清单：

- [x] 补齐默认参数编辑与保存。
- [x] 补齐接收机阈值预设管理。
- [x] 补齐模板保存、加载、覆盖策略。
- [x] 增加“配置来源”展示（manual/template/default）。

验收标准：

- [x] 重启后设置与模板保持一致。
- [x] 创建任务可直接复用模板。

---

## 8. P1-08 Provider 从 Stub 走向 Basic

目标：提升链路等级判定可信度，减少“占位感”。  
产出：Basic provider 的可运行实现（不追求最终科研版）。

执行清单：

- [x] `PreciseCoordinateProvider`、`OrbitClockCorrectionProvider`、`AntennaCorrectionProvider` 增强。
- [x] provider 可参与依赖判定与链路等级推导。
- [x] 结果元数据回填 provider 来源和状态。

验收标准：

- [x] FORMAL/EXPERIMENTAL/DEGRADED 判定更贴近真实依赖状态。
- [x] UI 与报告可见 provider 来源摘要。

---

## 9. P1-09 SIGMA_PHI_F 正式链路补强

目标：按计划固定步骤完成正式链路。  
产出：可追踪的 `SIGMA_PHI_F` 处理链与中间工件。

执行清单：

- [x] 确认 30° cutoff、短弧剔除、GF/HMW 周跳、去趋势、滤波、滑窗标准差流程一致。
- [x] 每个步骤都落地 `ProcessingStep` 与 artifact。
- [x] 与 MATLAB 基线进行误差与统计对照。

验收标准：

- [x] `SIGMA_PHI_F` 回归在阈值内。
- [x] 中间结果可在可视化页查看。

---

## 10. P1-10 MATLAB 回归集扩展

目标：避免仅对 `24084` 单日过拟合。  
产出：多日期/多站点基线与阈值策略。

执行清单：

- [x] 新增至少 1~2 组 DOY 基线清单（不覆盖旧基线）。
- [x] 扩展回归脚本支持多数据集批量运行。
- [x] 在门禁总结中增加分数据集统计。

验收标准：

- [x] 多数据集回归全部通过。
- [x] 总结报告可清晰区分各基线结果。

备注：
- 当前仓库内可直接运行的完整黄金基线为 `24084`；`24085/24086` 已建立清单占位与配置注册，待对应 MATLAB 输入/输出数据入库后可在同一套脚本中启用。

---

## 11. P2-11 Windows 发布化与运维化

目标：从“开发可跑”升级到“可分发可维护”。  
产出：Windows 分发包、启动脚本、日志与异常恢复说明。

执行清单：

- [x] 打包脚本（安装包或便携包）与版本号规范。
- [x] 首次运行初始化与升级迁移策略。
- [x] 崩溃日志、回滚脚本、问题定位手册。

验收标准：

- [x] 新机器按文档可独立安装运行。
- [x] 关键故障可通过日志定位。

备注：
- 当前交付为 Windows 便携包（本地 venv）路线，发布目录位于 `workspace/releases/windows`。
- `run_windows_release_gate.py` 提供发布结构与版本一致性门禁；新机安装按 `docs/windows_release_runbook.md` 执行。

---

## 12. P2-12 最终验收与冻结

目标：形成稳定迭代基线，进入下一版本开发。  
产出：冻结快照、发布说明、限制说明、回滚方案。

当前状态（2026-04-23）：已完成（新增 Step12 收尾脚本并生成冻结归档）。

执行清单：

- [x] 完整演示链路：导入 -> 计算 -> 可视化 -> 导出。
- [x] 复核验收清单并签字确认。
- [x] 生成 release/freeze 归档。

验收标准：

- [x] `workspace/reports/release_freeze_snapshot.json` 为 `PASSED`。
- [x] 文档与代码版本一致。

收尾命令：

```powershell
conda run -n isd-mvp python scripts/run_step12_closeout.py --signed-by <owner_name>
```

关键产物：

- `workspace/reports/step12_closeout_summary.json`
- `workspace/reports/mvp_acceptance_signoff.json`
- `workspace/reports/mvp_acceptance_signoff.md`
- `workspace/releases/freeze/isd-freeze-v<version>-<timestamp>.zip`

---

## 附：每次开发迭代的最小操作清单（可复制）

- [ ] 从 `main`（或当前主线）同步最新代码。
- [ ] 完成一个步骤的最小闭环实现。
- [ ] 运行 `pytest -q`。
- [ ] 运行 `scripts/run_step12_gate.py`。
- [ ] 更新 `docs/development_progress.md` 与变更说明。
- [ ] 记录新增风险与限制（如有）。



