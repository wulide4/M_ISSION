CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    root_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    data_range_start TEXT,
    data_range_end TEXT,
    default_output_path TEXT NOT NULL,
    tags_json TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stations (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    station_code TEXT NOT NULL,
    latitude REAL,
    longitude REAL,
    height REAL,
    systems_json TEXT NOT NULL,
    coverage_start TEXT,
    coverage_end TEXT,
    coordinate_source TEXT NOT NULL,
    receiver_model TEXT,
    receiver_manufacturer TEXT,
    firmware_version TEXT,
    antenna_model TEXT,
    antenna_calibration_source TEXT,
    is_scintillation_reference_station INTEGER NOT NULL,
    ppp_status TEXT NOT NULL,
    ppp_log_path TEXT,
    validation_summary TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS project_files (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    station_id TEXT,
    kind TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_name TEXT NOT NULL,
    rinex_version TEXT,
    sampling_interval_sec INTEGER,
    systems_json TEXT,
    file_date TEXT,
    matched INTEGER NOT NULL,
    validation_status TEXT NOT NULL,
    issues_json TEXT NOT NULL,
    metadata_json TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    task_type TEXT NOT NULL,
    chain_level TEXT NOT NULL,
    sampling_mode TEXT NOT NULL,
    config_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    created_from_template_id TEXT,
    summary TEXT,
    latest_error TEXT,
    snapshot_path TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS sub_tasks (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    station_id TEXT NOT NULL,
    date TEXT NOT NULL,
    system TEXT NOT NULL,
    metric_keys_json TEXT NOT NULL,
    status TEXT NOT NULL,
    current_step_key TEXT,
    duration_ms INTEGER,
    error_message TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS task_steps (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    sub_task_id TEXT,
    step_key TEXT NOT NULL,
    label TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    input_summary TEXT,
    output_summary TEXT,
    artifact_paths_json TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS task_logs (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    sub_task_id TEXT,
    timestamp TEXT NOT NULL,
    level TEXT NOT NULL,
    step_key TEXT,
    message TEXT NOT NULL,
    detail TEXT,
    log_file_path TEXT
);

CREATE TABLE IF NOT EXISTS validation_issues (
    id TEXT PRIMARY KEY,
    task_id TEXT,
    station_id TEXT,
    metric TEXT,
    level TEXT NOT NULL,
    code TEXT NOT NULL,
    message TEXT NOT NULL,
    detail TEXT,
    blocking INTEGER NOT NULL,
    recommendation TEXT
);

CREATE TABLE IF NOT EXISTS results (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    sub_task_id TEXT,
    project_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    station_id TEXT,
    system TEXT,
    satellite_prn TEXT,
    chain_level TEXT NOT NULL,
    sampling_mode TEXT NOT NULL,
    coordinate_source TEXT,
    receiver_model TEXT,
    threshold_source TEXT,
    parameter_source_summary TEXT NOT NULL,
    data_path TEXT NOT NULL,
    preview_image_path TEXT,
    stats_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    scope TEXT NOT NULL,
    is_default INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recent_items (
    id TEXT PRIMARY KEY,
    item_type TEXT NOT NULL,
    item_id TEXT NOT NULL,
    label TEXT NOT NULL,
    opened_at TEXT NOT NULL
);
