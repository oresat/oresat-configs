from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dacite import from_dict


@dataclass
class CardInfo:
    name: str
    """Unique name for the card."""
    nice_name: str
    """A nice name for the card."""
    node_id: int = 0x0
    """CANopen node id."""
    opd_address: int = 0x0
    """OPD address."""
    opd_always_on: bool = False
    """Keep the card on all the time. Only for battery cards."""
    child: str = ""
    """Optional child node name. Useful for CFC cards."""
    base: str = ""
    """Base type of card; e.g. "battery", "solar", ..."""
    common: str = ""
    """Common base type of card; e.g. "software" or "firmware"."""
    missions: list[str] = field(default_factory=list)
    """List of mission the card is in. Empty list for all."""

    @property
    def processor(self) -> str:
        processor = "none"
        if self.common == "software":
            processor = "octavo"
        elif self.common == "firmware":
            processor = "stm32"
        return processor


@dataclass
class ConfigInfo:
    name: str
    od_source: str


@dataclass
class CardsConfig:
    configs: list[ConfigInfo]
    cards: list[CardInfo]
    manager: CardInfo

    @classmethod
    def from_yaml(cls, config_path: str | Path) -> CardsConfig:
        if isinstance(config_path, str):
            config_path = Path(config_path)
        with config_path.open() as f:
            config_raw = yaml.safe_load(f)
        return from_dict(data_class=cls, data=config_raw)
