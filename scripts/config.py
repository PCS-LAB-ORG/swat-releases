"""Config loader — single responsibility: parse tools.yaml."""
from __future__ import annotations

from pathlib import Path

import yaml


def load_config(path: str = "config/tools.yaml") -> dict:
    return yaml.safe_load(Path(path).read_text())
