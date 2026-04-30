from __future__ import annotations

import re
import tomllib
from pathlib import Path

SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:[-+][0-9A-Za-z.-]+)?$")


def read_pyproject_version(project_root: Path) -> str:
    pyproject = project_root / "pyproject.toml"
    payload = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return str(payload.get("project", {}).get("version", "")).strip()


def read_package_version(project_root: Path) -> str:
    src_init = project_root / "src" / "isd" / "__init__.py"
    content = src_init.read_text(encoding="utf-8")
    marker = "__version__ = "
    for line in content.splitlines():
        if marker in line:
            return line.split(marker, 1)[1].strip().strip('"').strip("'")
    return ""


def validate_semver(version: str) -> bool:
    return bool(SEMVER_RE.match(str(version).strip()))

