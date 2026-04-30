from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from isd.infrastructure.repositories.settings_repository import SettingsRepository


DEFAULT_SETTINGS_KEY = "system"


class SettingsService:
    def __init__(self, settings_repo: SettingsRepository, config_dir: Path) -> None:
        self.settings_repo = settings_repo
        self.config_dir = config_dir

    def get(self) -> dict:
        defaults = self.get_defaults()
        loaded = self.settings_repo.get(DEFAULT_SETTINGS_KEY, default=None)
        if not isinstance(loaded, dict):
            return defaults
        merged = deepcopy(defaults)
        self._deep_update(merged, loaded)
        return merged

    def update(self, payload: dict) -> dict:
        current = self.get()
        incoming = payload if isinstance(payload, dict) else {}
        self._deep_update(current, incoming)
        self.settings_repo.set(DEFAULT_SETTINGS_KEY, current)
        return current

    def get_defaults(self) -> dict:
        ui_defaults = self._load_json(self.config_dir / "ui.defaults.json", {})
        algorithm_defaults = self._load_json(self.config_dir / "algorithm.defaults.json", {})
        threshold_presets = self._load_json(self.config_dir / "threshold.presets.json", {})
        frequency_mapping = self._load_json(self.config_dir / "frequency.mapping.json", {})
        return {
            "workspacePath": ui_defaults.get("workspacePath", "workspace"),
            "theme": ui_defaults.get("theme", "light"),
            "language": ui_defaults.get("language", "zh-CN"),
            "enableNonGpsSigmaPhiF": bool(ui_defaults.get("enableNonGpsSigmaPhiF", False)),
            "enableExperimental1sResample": bool(ui_defaults.get("enableExperimental1sResample", False)),
            "enableNavDegradedMode": bool(ui_defaults.get("enableNavDegradedMode", False)),
            "rinexApproxSigmaPhiFPolicy": ui_defaults.get("rinexApproxSigmaPhiFPolicy", "WARNING"),
            "defaultAlgorithmConfig": algorithm_defaults,
            "thresholdPresets": threshold_presets,
            "receiverThresholdPresets": {},
            "frequencyMapping": frequency_mapping,
            "defaultOutputPath": "workspace/outputs",
        }

    def _load_json(self, path: Path, fallback: Any) -> Any:
        if not path.exists():
            return fallback
        return json.loads(path.read_text(encoding="utf-8-sig"))

    def _deep_update(self, base: dict, patch: dict) -> None:
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                self._deep_update(base[key], value)
            else:
                base[key] = value
