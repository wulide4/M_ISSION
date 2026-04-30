# validateTask 规则对照矩阵（P0-03）

更新日期：2026-04-21  
实现位置：`src/isd/application/task_service.py`

## 1. 规则总览

| # | 规格规则 | 状态 | 规则码（示例） | 说明 |
|---|---|---|---|---|
| 1 | DIXSG 单站阻断 | 已实现 | `DIXSG_MULTI_STATION_REQUIRED` | 站点数 < 2 直接阻断 |
| 2 | 单站模式禁用区域栅格模式 | 已实现（等价） | `DIXSG_MULTI_STATION_REQUIRED` | 当前区域栅格由 DIXSG 表示，单站即阻断 |
| 3 | AATR 不进入标准事件检测流程 | 已实现 | `AATR_EVENT_DETECTION_DISABLED` | 以 WARNING 形式提示 |
| 4 | IAATR 仅弱事件/统计辅助 | 已实现 | `IAATR_WEAK_SUPPORT` | 以 WARNING 形式提示 |
| 5 | σϕf 不允许区域图模式 | 部分实现 | - | 当前任务模型无“区域图模式”开关，需 UI/TaskConfig 扩展后落地 |
| 6 | 非 GPS σϕf 仅实验模式可选 | 已实现 | `SIGMAPHI_NON_GPS_EXPERIMENTAL_ONLY` | 任务级实验开关未开时阻断 |
| 7 | 非 GPS σϕf 需全局实验治理开关 | 已实现 | `SIGMAPHI_NON_GPS_GLOBAL_DISABLED` | 系统设置未开启时阻断 |
| 8 | 非 GPS σϕf 启用后需风险标识 | 已实现 | `riskFlags: NON_GPS_SIGMAPHI_EXPERIMENT` | 任务/结果/报告走统一风险标识 |
| 9 | σϕf 缺 SP3/CLK/ATX 阻断 | 已实现 | `SIGMAPHI_NEED_SP3/CLK/ATX` | 缺依赖阻断，除非满足 NAV 降级 |
| 10 | 1s 流程需任务级开关 | 已实现 | `SAMPLING_1S_RESAMPLE_NOT_ENABLED` | 任务未开 `enable_1s_resample` 时阻断 |
| 11 | 1s 流程需全局治理开关 | 已实现 | `SAMPLING_1S_GLOBAL_DISABLED` | 系统设置未开时阻断 |
| 12 | 输出目录不可写阻断 | 已实现 | `OUTPUT_DIR_NOT_WRITABLE` | 创建/写入测试文件失败即阻断 |
| 13 | RINEX 近似坐标 + σϕf 受策略控制 | 已实现 | `RINEX_APPROX_SIGMAPHI_WARNING/BLOCKED` | 依据 `rinexApproxSigmaPhiFPolicy` 走 WARNING/BLOCKING |
| 14 | NAV fallback 仅手动开启降级模式时允许 | 已实现 | `NAV_FALLBACK_GLOBAL_DISABLED` | 任务开关 + 全局开关都满足才允许 |
| 15 | NAV fallback 可用时进入 DEGRADED | 已实现 | `NAV_FALLBACK_DEGRADED_MODE` | `derivedChainLevel` 自动降级 |
| 16 | 其他指标不得继承 σϕf 强拦截规则 | 已实现 | - | SP3/CLK/ATX 强拦截仅在 `SIGMA_PHI_F` 分支生效 |
| 17 | PPP 未完成按指标类型决策 | 已实现（σϕf） | `PPP_NOT_READY_SIGMAPHI_*` | 由 `ppp_fallback_strategy` 控制阻断或警告 |
| 18 | validateTask 输出统一字段 | 已实现 | - | 输出 `canRun/issues/derived*/riskFlags` |

## 2. 设置项映射

系统设置键（`settings.system`）：

- `enableNonGpsSigmaPhiF`
- `enableExperimental1sResample`
- `enableNavDegradedMode`
- `rinexApproxSigmaPhiFPolicy`（`WARNING` 或 `BLOCKING` 等）

默认值来源：`config/defaults/ui.defaults.json`

## 3. 已补齐测试

测试文件：`tests/test_task_validate.py`

新增覆盖点：

1. `NAV_FALLBACK_GLOBAL_DISABLED`
2. `RINEX_APPROX_SIGMAPHI_BLOCKED`
3. `SIGMAPHI_NON_GPS_GLOBAL_DISABLED`
4. `SAMPLING_1S_GLOBAL_DISABLED`

## 4. 后续待办（P1+）

1. 在 `TaskConfig` 明确引入“区域图模式开关”，补齐“σϕf 不允许区域图模式”的硬阻断。
2. 将“事件检测流程级别”从提示升级为可配置治理策略（AATR/IAATR）。
3. 增加规则覆盖率统计输出，纳入 `run_p0_gate.py` 汇总。

