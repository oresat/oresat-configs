from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from dacite import from_dict


@dataclass
class EdlCommandFieldConfig:
    name: str
    data_type: str
    description: str


@dataclass
class EdlCommandConfig:
    id: int
    name: str
    description: str
    request: list[EdlCommandFieldConfig] | None = None
    response: list[EdlCommandFieldConfig] | None = None


def load_edl_config(config_path: str | Path) -> list[EdlCommandConfig]:
    if isinstance(config_path, str):
        config_path = Path(config_path)
    with config_path.open() as f:
        config_raw = yaml.safe_load(f)
    return [from_dict(data_class=EdlCommandConfig, data=c) for c in config_raw["commands"]]
