from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import bitstring
import yaml
from dacite import from_dict

AX25_CALLSIGN_LEN = 6
AX25_HEADER_LEN = 16
AX25_PAYLOAD_MAX_LEN = 256


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
    fields: list[list[str]]
    """
    List of index and subindexes of objects from the C3's object dictionary to be added to the
    beacon.
    """


@dataclass
class MissionConfig:
    name: str
    nice_name: str
    id: int
    beacon: BeaconConfig

    @classmethod
    def from_yaml(cls, config_path: str | Path) -> MissionConfig:
        if isinstance(config_path, str):
            config_path = Path(config_path)
        with config_path.open() as f:
            config_raw = yaml.safe_load(f)
        return from_dict(data_class=cls, data=config_raw)


def pack_beacon_header(mission_config: MissionConfig) -> bytes:
    mission_id = mission_config.id
    beacon_revision = mission_config.beacon.revision
    ax25_config = mission_config.beacon.ax25
    if len(ax25_config.dest_callsign) > AX25_CALLSIGN_LEN:
        raise ValueError(f"dest callsign must be less than {AX25_CALLSIGN_LEN} chars")
    if ax25_config.dest_ssid < 0 or ax25_config.dest_ssid > 15:
        raise ValueError("dest callsign must be between 0 and 15")
    if len(ax25_config.src_callsign) > AX25_CALLSIGN_LEN:
        raise ValueError(f"src callsign must be less than {AX25_CALLSIGN_LEN} chars")
    if ax25_config.src_ssid < 0 or ax25_config.src_ssid > 15:
        raise ValueError("src callsign must be between 0 and 15")
    if ax25_config.control < 0 or ax25_config.control > 0xFF:
        raise ValueError("control must fit into a uint8")
    if ax25_config.pid < 0 or ax25_config.pid > 0xFF:
        raise ValueError("pid must fit into a uint8")
    if mission_id < 0 or mission_id > 0xFF:
        raise ValueError("mission_id must fit into a uint8")
    if beacon_revision < 0 or beacon_revision > 0xFF:
        raise ValueError("beacon_revision must fit into a uint8")

    # callsigns must be 6 chars, add trailing spaces as padding
    dest_callsign = ax25_config.dest_callsign
    dest_callsign += " " * (AX25_CALLSIGN_LEN - len(dest_callsign))
    src_callsign = ax25_config.src_callsign
    src_callsign += " " * (AX25_CALLSIGN_LEN - len(src_callsign))

    # move ssid to bits 4-1
    dest_ssid = ax25_config.dest_ssid
    dest_ssid <<= 1
    src_ssid = ax25_config.src_ssid
    src_ssid <<= 1

    # set reserve bits
    reserve_bits = 0b0110_0000
    dest_ssid |= reserve_bits
    src_ssid |= reserve_bits

    # set the c-bits
    dest_ssid |= int(ax25_config.command) << 7
    src_ssid |= int(ax25_config.response) << 7

    # set end of address bit
    src_ssid |= 1

    # make AX25 packet header
    # callsigns are bitshifted by 1
    header = (
        (bitstring.BitArray(dest_callsign.encode()) << 1).bytes
        + dest_ssid.to_bytes(1, "little")
        + (bitstring.BitArray(src_callsign.encode()) << 1).bytes
        + src_ssid.to_bytes(1, "little")
        + ax25_config.control.to_bytes(1, "little")
        + ax25_config.pid.to_bytes(1, "little")
    )

    payload_start = b"{{z" + mission_id.to_bytes(1, "little")
    payload_start += beacon_revision.to_bytes(1, "little")
    return header + payload_start
