# Ionospheric Scintillation Detection 开发计划记录

更新日期：2026-04-20

## 一、总体步骤排表（不按周）

1. 锁定 MATLAB 基线数据集（不可变）
目标：把 MATLAB 示例输入与输出固化为可追溯基线。  
产出：`config/datasets/matlab_24084_manifest.json`。  
验收：基线清单含文件哈希、站点列表、DOY `24084`（日期 `2024-03-24`）。

2. 建立 Python 样例工作区映射
目标：将 MATLAB 示例数据稳定映射到 Python 工程样例目录。  
产出：`workspace/samples/matlab_24084/...`。  
验收：一键同步、可重复执行、无脏数据。

3. 实现输入链完整解析（OBS/SP3/CLK/ATX/NAV）
目标：项目扫描能真实反映输入数据与依赖状态。  
产出：解析与匹配服务增强。  
验收：扫描后站点元数据与依赖摘要可见且正确。

4. 固化 `validateTask` 阻断规则
目标：所有关键阻断/警告规则统一在服务端校验。  
产出：规则实现 + 单测。  
验收：规则触发行为与规范一致。

5. 打通任务执行框架
目标：任务拆分、启动、暂停、恢复、停止、重试可完整运行。  
产出：任务状态流、日志流、快照落盘。  
验收：UI 可稳定跑完任务生命周期。

6. 迁移 ROTI/IAATR/AATR（可替换实现）
目标：先落工程可运行版，再逐步逼近 MATLAB。  
产出：指标结果与中间产物。  
验收：关键统计量在阈值内对齐基线。

7. 迁移 cROT + DIXSG
目标：完成区域指标和栅格链路。  
产出：网格结果与覆盖率统计。  
验收：覆盖率、异常段标记可对齐 MATLAB。

8. 迁移 GPS 正式链路 `σϕf`
目标：完成正式链路核心步骤。  
产出：`σϕf` 结果与预处理中间产物。  
验收：步骤可追踪，结果可回归。

9. 完成结果落盘策略
目标：统一 `NPZ/Parquet` 主格式并保留 `MAT` 导出。  
产出：结果存储与导出工具。  
验收：旧流程兼容与新流程可读并存。

10. 强化结果页
目标：补齐时序图、中间结果、区域栅格、详情卡。  
产出：结果闭环 UI。  
验收：导入→计算→可视化→导出闭环稳定。

11. 完成批处理/分析统计/报告中心/设置治理
目标：完成 E 阶段核心能力。  
产出：失败重试、模板、实验模式治理。  
验收：关键功能可演示、可复现。

12. 建立双轨回归（强制）
目标：每次算法改动都能对照 MATLAB 基线回归。  
产出：单测 + 回归 + E2E 套件。  
验收：三类测试全通过才可合并。

13. MVP 验收与冻结
目标：形成本地可运行、可演示的首发版本。  
产出：`MVP demo` 与操作说明。  
验收：无外部服务条件下跑通全流程。

## 二、步骤 1-3 落地清单

### 步骤 1：锁定 MATLAB 基线数据集

1. 新增脚本：`scripts/build_matlab_manifest.py`。  
2. 生成清单：`config/datasets/matlab_24084_manifest.json`。  
3. 清单范围固定为以下输入目录：  
`E:/2026_mapping_competition/M_ISSION-master/input_o_and_r file/24084`  
`E:/2026_mapping_competition/M_ISSION-master/input_sp3_file/24084`  
`E:/2026_mapping_competition/M_ISSION-master/input_clk_and_atx_file/24084`  
4. 对照基线输出目录固定为：  
`resROTI/GPSROTI24084`  
`resAATR/GPSAATR24084`  
`resRMSAATR/GPSRMSAATR24084`  
`ivcROT/GPScROT24084`  
`resDIXSG/GPSDIXSG24084`  
`resSIGMAPHI/GPSsigmaphi24084`  
5. 验收：清单包含文件哈希、大小、修改时间、站点列表、DOY 与绝对日期映射。

### 步骤 2：建立样例映射

1. 新增脚本：`scripts/sync_matlab_samples.py`。  
2. 建立目录：  
`workspace/samples/matlab_24084/raw/{obs,sp3,clk,atx,nav}`  
`workspace/samples/matlab_24084/golden/{roti,aatr,rmsaatr,crot,dixsg,sigmaphi}`  
3. 新增说明：`workspace/samples/matlab_24084/README.md`。  
4. 验收：同步可重复执行（幂等），清单校验失败时阻断后续流程。

### 步骤 3：输入链解析与匹配落地

1. 修改：`src/isd/infrastructure/filesystem/rinex_parser.py`。  
2. 修改：`src/isd/infrastructure/filesystem/file_scan.py`。  
3. 修改：`src/isd/infrastructure/filesystem/product_match.py`。  
4. 新增测试：`tests/test_input_chain_24084.py`。  
5. 新增脚本：`scripts/scan_matlab_24084.py`。  
6. 验收：  
扫描后可见真实站点、文件类型、依赖状态；  
`conda run -n isd-mvp pytest -q` 通过；  
`validateTask` 能基于真实依赖给出阻断/警告。

## 三、数据一致性约束（强制）

1. 当前阶段测试数据仅允许使用 MATLAB 示例输入，不引入新来源数据。  
2. 回归对照以 DOY `24084`（`2024-03-24`）为首个黄金基线。  
3. 若后续新增测试集，必须追加清单版本，不可覆盖现有基线。

