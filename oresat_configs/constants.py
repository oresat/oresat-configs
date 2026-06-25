"""
OreSat OD constants.

Seperate from __init__.py to avoid cirular imports.
"""

from dataclasses import InitVar, dataclass, field
from enum import Enum, unique
from importlib import resources
from importlib.abc import Traversable
from importlib.metadata import PackageNotFoundError, version
from types import ModuleType
from typing import Self

from . import base, oresat0, oresat0_5, oresat1

__all__ = [
    "Mission",
    "MissionConsts",
    "__version__",
]

try:
    __version__ = version("oresat-configs")
except PackageNotFoundError:
    __version__ = "0.0.0"  # package is not installed


@dataclass(frozen=True)
class MissionConsts:
    """A specific set of constants associated with an OreSat Mission."""

    id: int
    arg: str
    paths: InitVar[ModuleType]
    cards: Traversable = field(init=False)
    beacon: Traversable = field(init=False)
    standard: Traversable = field(init=False)
    common: dict[str, Traversable] = field(default_factory=dict, init=False)
    configs: dict[str, Traversable] = field(default_factory=dict, init=False)
    overlays: dict[str, Traversable] = field(default_factory=dict, init=False)

    def __post_init__(self, paths: ModuleType) -> None:
        mission = resources.files(paths)
        object.__setattr__(self, "cards", mission / "cards.csv")
        object.__setattr__(self, "beacon", mission / "beacon.yaml")
        for path in mission.iterdir():
            if path.name.endswith("_overlay.yaml"):
                card = path.name.removesuffix("_overlay.yaml")
                self.overlays[card] = path

        yaml = resources.files(base)
        for path in yaml.iterdir():
            if path.name == "standard_objects.yaml":
                object.__setattr__(self, "standard", yaml / "standard_objects.yaml")
            elif path.name.endswith("_common.yaml"):
                common = path.name.removesuffix("_common.yaml")
                self.common[common] = path
            elif path.name.endswith(".yaml"):
                self.configs[path.name.removesuffix(".yaml")] = path


@unique
class Mission(MissionConsts, Enum):
    """Each OreSat Mission and constant configuration data associated with them."""

    ORESAT0 = 1, "0", oresat0
    ORESAT0_5 = 2, "0.5", oresat0_5
    ORESAT1 = 3, "1", oresat1

    def __str__(self) -> str:
        return "OreSat" + self.arg

    def filename(self) -> str:
        """Return a string safe to use in filenames and other restricted settings.

        All lower case, dots replaced with underscores.
        """
        return str(self).lower().replace(".", "_")

    @classmethod
    def default(cls) -> Self:
        """Return the currently active Mission."""
        return cls.ORESAT1

    @classmethod
    def from_string(cls, val: str) -> Self:
        """Fetch the Mission associated with an appropriate string.

        Appropriate strings are the arg (0, 0.5, ...), optionally prefixed with
        OreSat or oresat.
        """
        arg = val.lower().removeprefix("oresat")
        for m in cls:
            if m.arg == arg:
                return m
        raise ValueError(f"invalid oresat mission: {val}")

    @classmethod
    def from_id(cls, val: int) -> Self:
        """Fetch the Mission associated with an appropriate ID.

        Appropriate IDs are integers 1, 2, ... that corespond to the specific
        mission. Note that these are not the number in the Satellite name.
        """
        for m in cls:
            if m.id == val:
                return m
        raise ValueError(f"invalid oresat mission ID: {val}")
