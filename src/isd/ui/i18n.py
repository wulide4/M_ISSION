"""Internationalization (i18n) module for bilingual Chinese/English support."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class LanguageManager(QObject):
    """Singleton language manager. All UI strings are stored here.
    Call switch() to toggle between zh_CN and en_US; all connected
    widgets receive the language_changed signal and should re-translate."""

    _instance: LanguageManager | None = None

    language_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.lang: str = "zh_CN"

    @classmethod
    def instance(cls) -> LanguageManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def switch(self) -> None:
        self.lang = "en_US" if self.lang == "zh_CN" else "zh_CN"
        self.language_changed.emit()

    def t(self, key: str) -> str:
        """Return translated string for *key* in the current language."""
        table = _TRANSLATIONS.get(key, {})
        return table.get(self.lang, table.get("zh_CN", key))


# ── Translation tables ──────────────────────────────────────────────
# Every key maps to {"zh_CN": ..., "en_US": ...}

_TRANSLATIONS: dict[str, dict[str, str]] = {
    # ── Main window & nav ──
    "app.title": {"zh_CN": "北斗/GNSS 电离层闪烁监测软件平台", "en_US": "BeiDou/GNSS Ionospheric Scintillation Monitoring Platform"},
    "nav.home": {"zh_CN": "首页", "en_US": "Home"},
    "nav.task": {"zh_CN": "任务管理", "en_US": "Task Management"},
    "nav.upload": {"zh_CN": "数据上传与处理", "en_US": "Data Upload & Processing"},
    "nav.preprocess": {"zh_CN": "数据预处理", "en_US": "Data Preprocessing"},
    "nav.visual": {"zh_CN": "结果可视化", "en_US": "Visualization"},
    "nav.analysis": {"zh_CN": "分析统计", "en_US": "Analysis & Statistics"},
    "nav.report": {"zh_CN": "报告中心", "en_US": "Report Center"},
    "nav.settings": {"zh_CN": "系统设置", "en_US": "Settings"},
    "lang.toggle": {"zh_CN": "EN", "en_US": "中文"},

    # ── Home page ──
    "home.welcome": {"zh_CN": "欢迎使用", "en_US": "Welcome"},
    "home.subtitle": {"zh_CN": "北斗/GNSS 电离层闪烁监测平台", "en_US": "BeiDou/GNSS Ionospheric Scintillation Monitoring Platform"},
    "home.card.upload.title": {"zh_CN": "数据上传", "en_US": "Data Upload"},
    "home.card.upload.desc": {"zh_CN": "上传OBS/SP3/ATX等数据文件", "en_US": "Upload OBS/SP3/ATX data files"},
    "home.card.visual.title": {"zh_CN": "结果可视化", "en_US": "Visualization"},
    "home.card.visual.desc": {"zh_CN": "查看闪烁指数计算结果", "en_US": "View scintillation index results"},
    "home.card.analysis.title": {"zh_CN": "分析统计", "en_US": "Analysis"},
    "home.card.analysis.desc": {"zh_CN": "统计分析闪烁事件", "en_US": "Statistical analysis of scintillation events"},
    "home.card.settings.title": {"zh_CN": "系统设置", "en_US": "Settings"},
    "home.card.settings.desc": {"zh_CN": "配置算法参数和阈值", "en_US": "Configure algorithm parameters & thresholds"},
    "home.quickstart": {"zh_CN": "快速开始", "en_US": "Quick Start"},
    "home.step1": {"zh_CN": "1. 进入「数据上传」页面，上传观测数据(OBS)、星历(SP3)、天线(ATX)文件", "en_US": "1. Go to \"Data Upload\" to upload OBS, SP3 and ATX files"},
    "home.step2": {"zh_CN": "2. 选择要计算的闪烁指数指标（默认ROTI）", "en_US": "2. Select scintillation indices to compute (default: ROTI)"},
    "home.step3": {"zh_CN": "3. 点击「开始处理」进行计算", "en_US": "3. Click \"Start Processing\" to compute"},
    "home.step4": {"zh_CN": "4. 在「结果可视化」页面查看时序图和统计结果", "en_US": "4. View time-series plots and statistics in \"Visualization\""},

    # ── Visualization page ──
    "vis.title": {"zh_CN": "结果可视化", "en_US": "Visualization"},
    "vis.select_task": {"zh_CN": "选择任务:", "en_US": "Select Task:"},
    "vis.select_task_placeholder": {"zh_CN": "-- 选择任务 --", "en_US": "-- Select Task --"},
    "vis.tab.series": {"zh_CN": "时序图", "en_US": "Time Series"},
    "vis.tab.grid": {"zh_CN": "区域栅格", "en_US": "Regional Grid"},
    "vis.tab.map": {"zh_CN": "区域地图", "en_US": "Regional Map"},
    "vis.tab.detail": {"zh_CN": "详情", "en_US": "Details"},
    "vis.btn.refresh": {"zh_CN": "刷新", "en_US": "Refresh"},
    "vis.btn.export": {"zh_CN": "导出", "en_US": "Export"},
    "vis.btn.clear": {"zh_CN": "清空结果", "en_US": "Clear Results"},
    "vis.status.loading": {"zh_CN": "状态: 加载中...", "en_US": "Status: Loading..."},
    "vis.status.loaded": {"zh_CN": "已加载 {0} 条结果", "en_US": "Loaded {0} results"},
    "vis.status.select_task": {"zh_CN": "请选择任务", "en_US": "Please select a task"},
    "vis.status.failed": {"zh_CN": "加载失败", "en_US": "Load failed"},
    "vis.status.no_data": {"zh_CN": "栅格数据不可用 ({0}): {1}", "en_US": "Grid data unavailable ({0}): {1}"},
    "vis.filter.station": {"zh_CN": "测站筛选:", "en_US": "Station:"},
    "vis.filter.system": {"zh_CN": "卫星系统:", "en_US": "GNSS System:"},
    "vis.filter.metric": {"zh_CN": "参数筛选:", "en_US": "Metric:"},
    "vis.filter.all": {"zh_CN": "全部", "en_US": "All"},

    # ── Detail card ──
    "detail.metric": {"zh_CN": "指标", "en_US": "Metric"},
    "detail.unit": {"zh_CN": "单位", "en_US": "Unit"},
    "detail.station": {"zh_CN": "站点", "en_US": "Station"},
    "detail.system": {"zh_CN": "系统", "en_US": "System"},
    "detail.chain": {"zh_CN": "链级", "en_US": "Chain Level"},
    "detail.sampling": {"zh_CN": "采样", "en_US": "Sampling"},
    "detail.coord_src": {"zh_CN": "坐标源", "en_US": "Coord Source"},
    "detail.threshold_src": {"zh_CN": "阈值源", "en_US": "Threshold Source"},
    "detail.stats": {"zh_CN": "统计", "en_US": "Statistics"},
    "detail.min": {"zh_CN": "最小值", "en_US": "Min"},
    "detail.max": {"zh_CN": "最大值", "en_US": "Max"},
    "detail.mean": {"zh_CN": "平均值", "en_US": "Mean"},
    "detail.missing": {"zh_CN": "缺失率", "en_US": "Missing Ratio"},
    "detail.threshold": {"zh_CN": "阈值", "en_US": "Threshold"},
    "detail.risk": {"zh_CN": "风险", "en_US": "Risk"},

    # ── Analysis page ──
    "ana.title": {"zh_CN": "分析统计", "en_US": "Analysis & Statistics"},
    "ana.col.metric": {"zh_CN": "指标名称", "en_US": "Metric"},
    "ana.col.count": {"zh_CN": "数量", "en_US": "Count"},
    "ana.col.min": {"zh_CN": "最小值", "en_US": "Min"},
    "ana.col.max": {"zh_CN": "最大值", "en_US": "Max"},
    "ana.col.mean": {"zh_CN": "均值", "en_US": "Mean"},
    "ana.col.threshold": {"zh_CN": "阈值", "en_US": "Threshold"},
    "ana.col.events": {"zh_CN": "事件总数", "en_US": "Total Events"},
    "ana.col.station": {"zh_CN": "站点", "en_US": "Station"},
    "ana.col.assessment": {"zh_CN": "评估", "en_US": "Assessment"},
    "ana.assess.exceeded": {"zh_CN": "超出阈值", "en_US": "Exceeded"},
    "ana.assess.partial": {"zh_CN": "部分超出", "en_US": "Partial"},
    "ana.assess.normal": {"zh_CN": "正常", "en_US": "Normal"},
    "ana.filter.metric": {"zh_CN": "指标筛选", "en_US": "Metric Filter"},
    "ana.filter.station": {"zh_CN": "站点筛选", "en_US": "Station Filter"},
    "ana.filter.all_metric": {"zh_CN": "全部指标", "en_US": "All Metrics"},
    "ana.filter.all_station": {"zh_CN": "全部站点", "en_US": "All Stations"},
    "ana.detail_title": {"zh_CN": "指标明细", "en_US": "Metric Details"},
    "ana.summary": {"zh_CN": "共 {0} 条结果，筛选后 {1} 条，涉及 {2} 个指标、{3} 个站点", "en_US": "{0} total results, {1} filtered, {2} metrics, {3} stations"},

    # ── Analysis metric names ──
    "metric.ROTI": {"zh_CN": "ROTI (电离层变化率总电子含量)", "en_US": "ROTI (Rate of TEC Index)"},
    "metric.AATR": {"zh_CN": "AATR (绝对电离层变化率)", "en_US": "AATR (Absolute TEC Rate)"},
    "metric.IAATR": {"zh_CN": "IAATR (瞬时绝对电离层变化率)", "en_US": "IAATR (Instantaneous AATR)"},
    "metric.DIXSG": {"zh_CN": "DIXSG (空间梯度扰动指数)", "en_US": "DIXSG (Disturbance Ionosphere Index)"},
    "metric.SIGMA_PHI_F": {"zh_CN": "σφf (振幅闪烁指数)", "en_US": "σφf (Phase Scintillation Index)"},
    "metric.S4C": {"zh_CN": "S4C (SNR幅度闪烁指数)", "en_US": "S4C (SNR Amplitude Scintillation Index)"},

    # ── Upload / process page ──
    "upload.title": {"zh_CN": "数据上传与处理", "en_US": "Data Upload & Processing"},
    "upload.file_section": {"zh_CN": "文件上传", "en_US": "File Upload"},
    "upload.obs_label": {"zh_CN": "* OBS观测数据:", "en_US": "* OBS Observation Data:"},
    "upload.sp3_label": {"zh_CN": "SP3星历数据 (σφf需要):", "en_US": "SP3 Ephemeris (for σφf):"},
    "upload.atx_label": {"zh_CN": "ATX天线数据 (σφf需要):", "en_US": "ATX Antenna Data (for σφf):"},
    "upload.clk_label": {"zh_CN": "CLK钟差数据:", "en_US": "CLK Clock Data:"},
    "upload.nav_label": {"zh_CN": "NAV导航数据:", "en_US": "NAV Navigation Data:"},
    "upload.add_btn": {"zh_CN": "添加", "en_US": "Add"},
    "upload.metric_section": {"zh_CN": "闪烁指数计算", "en_US": "Scintillation Index Computation"},
    "upload.metric_hint": {"zh_CN": "选择要计算的指标 (绿色 = 数据满足计算条件, 红色 = 数据不足)", "en_US": "Select indices (Green = data sufficient, Red = insufficient)"},
    "upload.metric.roti.desc": {"zh_CN": "TEC变化率指数 (需OBS双频数据)", "en_US": "TEC Rate of Change Index (needs dual-freq OBS)"},
    "upload.metric.aatr.desc": {"zh_CN": "沿弧TEC变化率 (需OBS双频数据)", "en_US": "Along-Arc TEC Rate (needs dual-freq OBS)"},
    "upload.metric.iaatr.desc": {"zh_CN": "瞬时AATR (需OBS双频数据)", "en_US": "Instantaneous AATR (needs dual-freq OBS)"},
    "upload.metric.dixsg.desc": {"zh_CN": "差分电离层梯度 (需≥2站点)", "en_US": "Differential Ionospheric Gradient (needs ≥2 stations)"},
    "upload.metric.sigma.desc": {"zh_CN": "相位闪烁指数 (需OBS+ATX+SP3)", "en_US": "Phase Scintillation Index (needs OBS+ATX+SP3)"},
    "upload.metric.s4c.desc": {"zh_CN": "SNR幅度闪烁指数 (需OBS双频SNR数据)", "en_US": "SNR Amplitude Scintillation Index (needs dual-freq SNR)"},
    "upload.status_section": {"zh_CN": "状态", "en_US": "Status"},
    "upload.status.waiting": {"zh_CN": "请上传必要的文件", "en_US": "Please upload required files"},
    "upload.status.waiting_obs": {"zh_CN": "请上传必要的文件 (至少需要OBS观测数据)", "en_US": "Please upload files (at least OBS data required)"},
    "upload.status.ready": {"zh_CN": "文件已就绪 ({0})", "en_US": "Files ready ({0})"},
    "upload.process_btn": {"zh_CN": "上传并开始处理", "en_US": "Upload & Process"},
    "upload.clear_btn": {"zh_CN": "清空全部", "en_US": "Clear All"},

    # ── Preprocessing (sky plot) ──
    "preprocess.title": {"zh_CN": "数据预处理", "en_US": "Data Preprocessing"},
    "preprocess.section": {"zh_CN": "预处理视图", "en_US": "Preprocessing View"},
    "preprocess.sky_plot": {"zh_CN": "星空图", "en_US": "Sky Plot"},
    "preprocess.elev_chart": {"zh_CN": "卫星仰角-时间图", "en_US": "Satellite Elevation vs Time"},
    "preprocess.sat_count": {"zh_CN": "卫星数量图", "en_US": "Satellite Count"},
    "preprocess.select_station": {"zh_CN": "选择测站:", "en_US": "Select Station:"},
    "preprocess.select_system": {"zh_CN": "选择系统:", "en_US": "Select System:"},
    "preprocess.load_data": {"zh_CN": "加载预处理数据", "en_US": "Load Preprocessing Data"},
    "preprocess.no_data": {"zh_CN": "无预处理数据，请先上传并处理数据", "en_US": "No preprocessing data. Upload and process data first."},

    # ── Settings page ──
    "set.title": {"zh_CN": "系统设置", "en_US": "Settings"},
    "set.basic": {"zh_CN": "基本参数", "en_US": "Basic Parameters"},
    "set.algo": {"zh_CN": "算法参数", "en_US": "Algorithm Parameters"},
    "set.dixsg": {"zh_CN": "DIXSG参数 (空间梯度扰动指数)", "en_US": "DIXSG Parameters (Spatial Gradient Index)"},
    "set.cycle_slip": {"zh_CN": "周跳检测参数 (TurboEdit)", "en_US": "Cycle Slip Detection (TurboEdit)"},
    "set.threshold": {"zh_CN": "阈值配置", "en_US": "Threshold Configuration"},
    "set.enable_nav": {"zh_CN": "启用NAV降级模式", "en_US": "Enable NAV Degraded Mode"},
    "set.enable_resample": {"zh_CN": "启用1s重采样", "en_US": "Enable 1s Resampling"},
    "set.enable_non_gps_sigma": {"zh_CN": "启用非GPS σϕf 实验模式", "en_US": "Enable Non-GPS σϕf Experimental Mode"},
    "set.default_output": {"zh_CN": "默认输出路径", "en_US": "Default Output Path"},
    "set.cutoff": {"zh_CN": "截止高度角(°)", "en_US": "Cutoff Elevation (°)"},
    "set.roti_window": {"zh_CN": "ROTI窗口(min)", "en_US": "ROTI Window (min)"},
    "set.sigma_window": {"zh_CN": "σφf窗口(min)", "en_US": "σφf Window (min)"},
    "set.bw_order": {"zh_CN": "Butterworth阶数", "en_US": "Butterworth Order"},
    "set.bw_low": {"zh_CN": "低频截止(Hz)", "en_US": "Low Cutoff (Hz)"},
    "set.bw_high": {"zh_CN": "高频截止(Hz)", "en_US": "High Cutoff (Hz)"},
    "set.dixsg.levels": {"zh_CN": "灵敏度等级数", "en_US": "Sensitivity Levels"},
    "set.dixsg.first": {"zh_CN": "起始灵敏度", "en_US": "First Sensitivity"},
    "set.dixsg.step": {"zh_CN": "灵敏度步长", "en_US": "Sensitivity Step"},
    "set.dixsg.max_dist": {"zh_CN": "最大基线距离(km)", "en_US": "Max Baseline (km)"},
    "set.dixsg.grid": {"zh_CN": "网格大小(°)", "en_US": "Grid Size (°)"},
    "set.dixsg.lat": {"zh_CN": "纬度范围", "en_US": "Latitude Range"},
    "set.dixsg.lon": {"zh_CN": "经度范围", "en_US": "Longitude Range"},
    "set.cs.window": {"zh_CN": "检测窗口(历元)", "en_US": "Detection Window (epochs)"},
    "set.cs.gf": {"zh_CN": "GF阈值因子", "en_US": "GF Threshold Factor"},
    "set.cs.hmw": {"zh_CN": "HMW阈值因子 (×σ)", "en_US": "HMW Threshold Factor (×σ)"},
    "set.cs.min_obs": {"zh_CN": "最小统计样本数", "en_US": "Min Observations for Stats"},
    "set.cs.min_arc": {"zh_CN": "最短弧段(历元)", "en_US": "Min Arc Length (epochs)"},
    "set.btn.load": {"zh_CN": "加载", "en_US": "Load"},
    "set.btn.save": {"zh_CN": "保存", "en_US": "Save"},
    "set.btn.reset": {"zh_CN": "重置", "en_US": "Reset"},

    # ── Report page ──
    "rpt.title": {"zh_CN": "报告中心", "en_US": "Report Center"},
    "rpt.settings": {"zh_CN": "报告设置", "en_US": "Report Settings"},
    "rpt.project_id": {"zh_CN": "项目ID", "en_US": "Project ID"},
    "rpt.template": {"zh_CN": "模板", "en_US": "Template"},
    "rpt.report_title": {"zh_CN": "标题", "en_US": "Title"},
    "rpt.output_path": {"zh_CN": "输出路径", "en_US": "Output Path"},
    "rpt.include_stats": {"zh_CN": "包含统计摘要", "en_US": "Include Statistics Summary"},
    "rpt.include_params": {"zh_CN": "包含参数配置", "en_US": "Include Parameter Config"},
    "rpt.open_after": {"zh_CN": "导出后打开报告", "en_US": "Open Report After Export"},
    "rpt.btn.load": {"zh_CN": "加载结果", "en_US": "Load Results"},
    "rpt.btn.browse": {"zh_CN": "选择路径", "en_US": "Browse"},
    "rpt.btn.preview": {"zh_CN": "预览报告", "en_US": "Preview Report"},
    "rpt.btn.export": {"zh_CN": "导出报告", "en_US": "Export Report"},
    "rpt.select_results": {"zh_CN": "选择结果（可多选）", "en_US": "Select Results (multi-select)"},
    "rpt.default_title": {"zh_CN": "闪烁指数监测报告", "en_US": "Scintillation Monitoring Report"},

    # ── Task management page ──
    "task.title": {"zh_CN": "任务管理", "en_US": "Task Management"},
    "task.btn.refresh": {"zh_CN": "刷新", "en_US": "Refresh"},
    "task.btn.stop": {"zh_CN": "停止", "en_US": "Stop"},
    "task.btn.delete": {"zh_CN": "删除任务", "en_US": "Delete Task"},
    "task.btn.cleanup": {"zh_CN": "清理已完成", "en_US": "Cleanup Completed"},
    "task.status.load_failed": {"zh_CN": "加载失败", "en_US": "Load failed"},
    "task.status.summary": {"zh_CN": "共 {0} 个任务 | 运行中: {1} | 已完成: {2}", "en_US": "{0} tasks | Running: {1} | Completed: {2}"},
    "task.warn.select_stop": {"zh_CN": "请先选择要停止的任务", "en_US": "Please select a task to stop"},
    "task.warn.select_delete": {"zh_CN": "请先选择要删除的任务", "en_US": "Please select a task to delete"},
    "task.confirm.delete": {"zh_CN": "确定要删除任务 {0} 吗？\n这将删除所有相关数据且无法恢复。", "en_US": "Delete task {0}?\nAll related data will be permanently removed."},
    "task.error.delete_failed": {"zh_CN": "删除失败: {0}", "en_US": "Delete failed: {0}"},
    "task.confirm.cleanup": {"zh_CN": "确定要删除所有已取消和已完成的任务吗？\n这将删除所有相关数据且无法恢复。", "en_US": "Delete all cancelled and completed tasks?\nAll related data will be permanently removed."},
    "task.info.deleted": {"zh_CN": "已删除 {0} 个任务", "en_US": "Deleted {0} task(s)"},

    # ── Data calc page ──
    "calc.title": {"zh_CN": "数据计算", "en_US": "Data Calculation"},
    "calc.task_params": {"zh_CN": "任务参数", "en_US": "Task Parameters"},
    "calc.station_select": {"zh_CN": "站点选择（可鼠标多选）", "en_US": "Station Selection (multi-select)"},

    # ── Common dialogs ──
    "dlg.confirm": {"zh_CN": "确认", "en_US": "Confirm"},
    "dlg.confirm_clear": {"zh_CN": "确定要清空所有结果吗？\n此操作不可恢复。", "en_US": "Clear all results?\nThis cannot be undone."},
    "dlg.warning": {"zh_CN": "警告", "en_US": "Warning"},
    "dlg.error": {"zh_CN": "错误", "en_US": "Error"},
    "dlg.success": {"zh_CN": "成功", "en_US": "Success"},
    "dlg.yes": {"zh_CN": "是", "en_US": "Yes"},
    "dlg.no": {"zh_CN": "否", "en_US": "No"},

    # ── Grid axis labels ──
    "grid.lon_label": {"zh_CN": "经度 (°E)", "en_US": "Longitude (°E)"},
    "grid.lat_label": {"zh_CN": "纬度 (°N)", "en_US": "Latitude (°N)"},

    # ── Export dialog ──
    "export.title": {"zh_CN": "导出结果", "en_US": "Export Result"},
    "export.select_result": {"zh_CN": "请先选择结果", "en_US": "Please select a result first"},
    "export.done": {"zh_CN": "导出完成", "en_US": "Export complete"},
    "export.failed": {"zh_CN": "导出失败", "en_US": "Export failed"},

    # ── Status messages ──
    "status.ready": {"zh_CN": "就绪", "en_US": "Ready"},

    # ── Upload page - dynamic status / progress messages ──
    "upload.dlg.select_file": {"zh_CN": "选择{0}文件", "en_US": "Select {0} Files"},
    "upload.status.no_obs": {"zh_CN": "请上传必要的文件 (至少需要OBS观测数据)", "en_US": "Please upload required files (at least OBS data required)"},
    "upload.status.files_ready": {"zh_CN": "文件已就绪 ({0})", "en_US": "Files ready ({0})"},
    "upload.status.please_upload_required": {"zh_CN": "请上传必要的文件 (带*号的为必填)", "en_US": "Please upload required files (* marks required)"},
    "upload.status.stopped_tasks": {"zh_CN": "已停止 {0} 个运行中的任务", "en_US": "Stopped {0} running task(s)"},
    "upload.warn.no_obs": {"zh_CN": "请上传至少OBS观测数据文件", "en_US": "Please upload at least OBS observation data"},
    "upload.warn.no_metric": {"zh_CN": "请至少选择一个可用的闪烁指标", "en_US": "Please select at least one available scintillation index"},
    "upload.warn.no_file": {"zh_CN": "请先选择输入文件", "en_US": "Please select input files first"},
    "upload.progress.creating_project": {"zh_CN": "正在创建项目...", "en_US": "Creating project..."},
    "upload.progress.scanning_files": {"zh_CN": "正在扫描文件...", "en_US": "Scanning files..."},
    "upload.progress.creating_task": {"zh_CN": "正在创建任务...", "en_US": "Creating task..."},
    "upload.progress.task_started": {"zh_CN": "任务已启动: {0}", "en_US": "Task started: {0}"},
    "upload.progress.processing": {"zh_CN": "处理中... 任务ID: {0}", "en_US": "Processing... Task ID: {0}"},
    "upload.progress.task_completed": {"zh_CN": "任务已完成!", "en_US": "Task completed!"},
    "upload.status.task_completed": {"zh_CN": "任务已完成", "en_US": "Task completed"},
    "upload.progress.task_failed": {"zh_CN": "任务失败", "en_US": "Task failed"},
    "upload.status.task_failed": {"zh_CN": "任务失败: {0}", "en_US": "Task failed: {0}"},
    "upload.progress.initializing": {"zh_CN": "正在初始化任务...", "en_US": "Initializing task..."},
    "upload.progress.running": {"zh_CN": "处理中... {0}/{1} ({2}%)", "en_US": "Processing... {0}/{1} ({2}%)"},
    "upload.progress.status": {"zh_CN": "状态: {0}", "en_US": "Status: {0}"},
    "upload.error.create_project": {"zh_CN": "创建项目失败", "en_US": "Failed to create project"},
    "upload.error.scan_files": {"zh_CN": "文件扫描失败", "en_US": "Failed to scan files"},
    "upload.error.no_station": {"zh_CN": "扫描完成但未识别到有效站点", "en_US": "Scan completed but no valid stations found"},
    "upload.error.validate_failed": {"zh_CN": "任务校验失败", "en_US": "Task validation failed"},
    "upload.error.validate_blocked": {"zh_CN": "任务校验未通过", "en_US": "Task validation blocked"},
    "upload.error.validate_blocked_detail": {"zh_CN": "任务校验未通过:\n{0}", "en_US": "Task validation blocked:\n{0}"},
    "upload.error.create_task": {"zh_CN": "创建任务失败", "en_US": "Failed to create task"},
    "upload.warn.start_failed": {"zh_CN": "任务创建成功但启动失败，请手动开始", "en_US": "Task created but failed to start. Please start manually"},
    "upload.info.station": {"zh_CN": "站点", "en_US": "Stations"},
    "upload.info.system": {"zh_CN": "系统", "en_US": "Systems"},
    "upload.info.date_to": {"zh_CN": "至", "en_US": "to"},
    "upload.info.warning_prefix": {"zh_CN": "警告", "en_US": "Warning"},
    "upload.info.unknown_error": {"zh_CN": "未知错误", "en_US": "Unknown error"},
    "upload.info.unknown_blocking": {"zh_CN": "未知阻断", "en_US": "Unknown blocking issue"},
}


def tr(key: str) -> str:
    """Shortcut for LanguageManager.instance().t(key)."""
    return LanguageManager.instance().t(key)
