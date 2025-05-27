"""Load a beacon config file."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from dacite import from_dict
from yaml import CLoader, load


@dataclass
class BeaconAx25Config:
    """
    AX.25 beacon config section.

    Example:

    .. code-block:: yaml

        ax25:
          dest_callsign: SPACE
          dest_ssid: 0
          src_callsign: KJ7SAT
          src_ssid: 0
          control: 0x3 # ui-frame
          pid: 0xf0 # no L3 protocol
          command: false
          response: false
    """

    dest_callsign: str
    """Destination callsign."""
    dest_ssid: int
    """Destination SSID. 0-15."""
    src_callsign: str
    """Source callsign."""
    src_ssid: int
    """Soure SSID. 0-15."""
    control: int
    """AX.25 control field enum."""
    pid: int
    """Ax.25 PID field name."""
    command: bool
    """If set to True, the C-bit in destination field."""
    response: bool
    """If set to True, the C-bit in source field."""


@dataclass
class BeaconConfig:
    """
    Beacon config.

    Example:

    .. code-block:: yaml

        revision: 0
        ax25:
          dest_callsign: SPACE
          dest_ssid: 0
          src_callsign: KJ7SAT
          src_ssid: 0
          ...
        fields:
          - [beacon, start_chars]
          - [satellite_id]
          - [beacon, revision]
          ...
    """

    revision: int
    """Beacon revision number."""
    ax25: BeaconAx25Config
    """AX.25 configs section."""
    fields: list[list[str]] = field(default_factory=list)
    """
    List of index and subindexes of objects from the C3's object dictionary to be added to the
    beacon.
    """

    @classmethod
    def from_yaml(cls, config_path: Path) -> BeaconConfig:
        """Load a beacon YAML config file."""

        with config_path.open() as f:
            config_raw = load(f, Loader=CLoader)
        return from_dict(data_class=cls, data=config_raw)
