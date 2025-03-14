from dataclasses import dataclass, field

from dacite import from_dict
from yaml import CLoader, load

from .constants import Mission


@dataclass
class Card:
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
    missions: list[str] = field(default_factory=lambda: [m.filename() for m in Mission])
    """List of mission the card is in."""

    @property
    def processor(self) -> str:
        processor = "none"
        if self.common == "software":
            processor = "octavo"
        elif self.common == "firmware":
            processor = "stm32"
        return processor


def load_cards_config(path: str) -> list[Card]:
    with open(path) as f:
        config_raw = load(f, Loader=CLoader)
    return [from_dict(data_class=Card, data=card_raw) for card_raw in config_raw]
