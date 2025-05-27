"""Utilities for top level cards definitions, not in the OD"""

import csv
from dataclasses import InitVar, dataclass, field, fields
from importlib import abc, resources
from pathlib import Path
from typing import Optional

from . import base


@dataclass
class Card:
    """Card info."""

    name: InitVar[str]
    nice_name: str
    """A nice name for the card."""
    node_id: int
    """CANopen node id."""
    processor: str
    """Processor type; e.g.: "octavo", "stm32", or "none"."""
    opd_address: int
    """OPD address."""
    opd_always_on: bool
    """Keep the card on all the time. Only for battery cards."""
    child: str = ""
    """Optional child node name. Useful for CFC cards."""
    base: str = field(init=False)
    """Base type of card; e.g. "battery", "solar", ..."""
    common: Optional[abc.Traversable] = field(init=False)
    """Path to the card's common (sw or fw) config"""
    config: Optional[abc.Traversable] = field(init=False)
    """Path to the card specific config"""

    def __post_init__(self, name):
        if name in ("cfc_processor", "cfc_sensor"):
            basename = "cfc"
        elif name.startswith("rw"):
            basename = "reaction_wheel"
        elif name[-1].isdigit():
            basename = name.rsplit(sep="_", maxsplit=1)[0]
        else:
            basename = name

        basedir = resources.files(base)

        if self.processor == "none":
            common = None
        elif self.processor == "octavo":
            common = basedir / "sw_common.yaml"
        elif self.processor == "stm32":
            common = basedir / "fw_common.yaml"
        else:
            raise ValueError(f"Invalid processor {self.processor}")

        if self.processor == "none":
            config = None
        else:
            config = basedir / (basename + ".yaml")

        object.__setattr__(self, "base", basename)
        object.__setattr__(self, "common", common)
        object.__setattr__(self, "config", config)


def cards_from_csv(path: Path) -> dict[str, Card]:
    """Turns cards.csv into a dict of names->Cards, filtered by the current mission"""

    with path.open() as f:
        reader = csv.DictReader(f)
        cols = set(reader.fieldnames) if reader.fieldnames else set()
        expect = {f.name for f in fields(Card)}
        expect.add("name")  # the 'name' column is the keys of the returned dict; not in Card
        expect -= {"base", "common", "config"}  # these fields are derived; not in csv
        if cols - expect:
            raise TypeError(f"{path} has excess columns: {cols - expect}. Update class Card?")
        if expect - cols:
            raise TypeError(f"class Card expects more columns than {path} has: {expect - cols}")

        return {
            row["name"]: Card(
                row["name"],
                row["nice_name"],
                int(row["node_id"], 16),
                row["processor"],
                int(row["opd_address"], 16),
                row["opd_always_on"].lower() == "true",
                row["child"],
            )
            for row in reader
        }
