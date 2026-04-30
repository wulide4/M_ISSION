from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ISD_", env_file=".env", extra="ignore")

    app_name: str = "Ionospheric Scintillation Detection"
    workspace_path: Path = Path("workspace")
    database_path: Path = Path("workspace/isd.sqlite3")
    log_dir: Path = Path("workspace/logs")


settings = AppSettings()
