from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class WorkspacePaths:
    root: Path

    def ensure(self) -> None:
        for d in [
            "projects",
            "outputs",
            "cache",
            "logs",
            "temp",
            "reports",
            "samples",
        ]:
            (self.root / d).mkdir(parents=True, exist_ok=True)

    def project_dir(self, project_id: str) -> Path:
        return self.root / "projects" / project_id

    def task_dir(self, project_id: str, task_id: str) -> Path:
        return self.project_dir(project_id) / "tasks" / task_id
