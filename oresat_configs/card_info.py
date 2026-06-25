"""Utilities for top level cards definitions, not in the OD."""

import csv
from dataclasses import dataclass, fields
from importlib.abc import Traversable
from typing import Literal


@dataclass(frozen=True)
class Card:
    """Card info."""

    name: str
    """The standard name of the card"""
    nice_name: str
    """A nice name for the card."""
    node_id: int
    """CANopen node id."""
    processor: str
    """Processor type; e.g.: "octavo", "stm32", "mcxn", or "none"."""
    opd_address: int
    """OPD address."""
    opd_always_on: bool
    """Keep the card on all the time. Only for battery cards."""
    child: str = ""
    """Optional child node name. Useful for CFC cards."""

    @property
    def basename(self) -> str:
        """Base name of card; e.g. "battery", "solar", ..."""
        match self.name:
            case "cfc_processor" | "cfc_sensor":
                return "cfc"
            case x if x.startswith("rw"):
                return "reaction_wheel"
            case x if x[-1].isdigit():
                return x.rsplit(sep="_", maxsplit=1)[0]
            case x:
                return x

    @property
    def basetype(self) -> Literal['sw', 'fw'] | None:
        """Type of software on the card.

        Determines the common interface presented by CANopen.

        Returns
        -------
        fw if it's an embedded card (ChibiOS/Zephyr).
        sw if it's a linux card.
        None if there is no processor on this card.
        """
        match self.processor:
            case "none":
                return None
            case "octavo":
                return "sw"
            case "stm32" | "mcxn":
                return "fw"
            case _:
                raise ValueError(f"Invalid processor {self.processor}")


def cards_from_csv(path: Traversable) -> dict[str, Card]:
    """Turn cards.csv into a dict of names->Cards, filtered by the current mission."""
    with path.open() as f:
        reader = csv.DictReader(f)
        cols = set(reader.fieldnames) if reader.fieldnames else set()
        expect = {f.name for f in fields(Card) if f.init}
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
