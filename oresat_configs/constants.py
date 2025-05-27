"""
OreSat OD constants

Seperate from __init__.py to avoid cirular imports.
"""

from __future__ import annotations

from dataclasses import InitVar, dataclass, field
from enum import Enum, unique
from importlib import abc, resources
from types import ModuleType

from . import oresat0, oresat0_5, oresat1

__all__ = [
    "__version__",
    "MissionConsts",
    "Mission",
]

try:
    from ._version import version as __version__  # type: ignore
except ImportError:
    __version__ = "0.0.0"  # package is not installed


@dataclass(frozen=True)
class MissionConsts:
    """A specific set of constants associated with an OreSat Mission"""

    id: int
    arg: str
    paths: InitVar[ModuleType]
    cards: abc.Traversable = field(init=False)
    beacon: abc.Traversable = field(init=False)
    overlays: dict[str, abc.Traversable] = field(default_factory=dict, init=False)

    def __post_init__(self, paths):
        base = resources.files(paths)
        object.__setattr__(self, "cards", base / "cards.csv")
        object.__setattr__(self, "beacon", base / "beacon.yaml")
        for path in base.iterdir():
            if path.name.endswith("_overlay.yaml"):
                card = path.name.rsplit(sep="_", maxsplit=1)[0]
                self.overlays[card] = path


@unique
class Mission(MissionConsts, Enum):
    """Each OreSat Mission and constant configuration data associated with them"""

    ORESAT0 = 1, "0", oresat0
    ORESAT0_5 = 2, "0.5", oresat0_5
    ORESAT1 = 3, "1", oresat1

    def __str__(self) -> str:
        return "OreSat" + self.arg

    def filename(self) -> str:
        """Returns a string safe to use in filenames and other restricted settings.

        All lower case, dots replaced with underscores.
        """
        return str(self).lower().replace(".", "_")

    @classmethod
    def default(cls) -> Mission:
        """Returns the currently active mission"""
        return cls.ORESAT0_5

    @classmethod
    def from_string(cls, val: str) -> Mission:
        """Fetches the Mission associated with an appropriate string

        Appropriate strings are the arg (0, 0.5, ...), optionally prefixed with
        OreSat or oresat
        """
        arg = val.lower().removeprefix("oresat")
        for m in cls:
            if m.arg == arg:
                return m
        raise ValueError(f"invalid oresat mission: {val}")

    @classmethod
    def from_id(cls, val: int) -> Mission:
        """Fetches the Mission associated with an appropriate ID

        Appropriate IDs are integers 1, 2, ... that corespond to the specific
        mission. Note that these are not the number in the Satellite name.
        """
        for m in cls:
            if m.id == val:
                return m
        raise ValueError(f"invalid oresat mission ID: {val}")
