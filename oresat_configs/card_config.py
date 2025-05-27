"""Load a card config file."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any, Optional, Union

from dacite import from_dict
from yaml import CLoader, load


@dataclass
class ConfigObject:
    """Object in config."""

    data_type: str = "uint32"
    """Data type of the object."""
    length: int = 1
    """Length of an octet string object (only used when `data_type` is set to ``"octet_str"``)."""
    access_type: str = "rw"
    """
    Access type of object over the CAN bus, can be ``"rw"``, ``"ro"``, ``"wo"``, or ``"const"``.
    """
    default: Any = None
    """Default value of object."""
    description: str = ""
    """Description of object."""
    value_descriptions: dict[str, int] = field(default_factory=dict)
    """Optional: Can be used to define enum values for an unsigned integer data types."""
    bit_definitions: dict[str, Union[int, str]] = field(default_factory=dict)
    """Optional: Can be used to define bitfield of an unsigned integer data types."""
    unit: str = ""
    """Optional engineering unit for the object."""
    scale_factor: float = 1
    """Can be used to scale a integer value to a engineering (float) value."""
    low_limit: Optional[int] = None
    """
    The lower raw limit for value. No need to set this if it limit is the lower limit of the data
    type.
    """
    high_limit: Optional[int] = None
    """
    The higher raw limit for value. No need to set this if it limit is the higher limit of the data
    type.
    """


@dataclass
class GenerateSubindex(ConfigObject):
    """
    Used to generate subindexes for an array.

    Example:

    .. code-block:: yaml

      - index: 0x4000
        name: my_array
        object_type: array
        generate_subindexes:
            subindexes: fixed_length
            name: item
            length: 10
            data_type: uint16
            access_type: ro
            unit: C
            scale_factor: 0.001

    will generate the equivalent of

    .. code-block:: yaml

      - index: 0x4000
        name: my_array
        object_type: array
        subindexes:
        generate_subindexes:
        - subindex: 1
          name: item_1
          data_type: uint16
          access_type: ro
          unit: C
          scale_factor: 0.001
        - subindex: 2
          name: item_2
          data_type: uint16
          access_type: ro
          unit: C
          scale_factor: 0.001
        ...
        - subindex: 9
          name: item_9
          data_type: uint16
          access_type: ro
          unit: C
          scale_factor: 0.001
        - subindex: 10
          name: item_10
          data_type: uint16
          access_type: ro
          unit: C
          scale_factor: 0.001
    """

    name: str = ""
    """Names of objects to generate."""
    subindexes: Union[str, int] = 0
    """Subindexes of objects to generate."""


@dataclass
class SubindexObject(ConfigObject):
    """
    Object at subindex.

    Example:

    .. code-block:: yaml

        subindex: 0x1
        name: length
        data_type: uint8
        description: number of files in fread cache
        access_type: ro
    """

    name: str = ""
    """Name of object, must be in lower_snake_case."""
    subindex: int = 0
    """
    Subindex of object, start at subindex 1 (subindex 0 aka highest_index_supported will be
    generated).
    """


@dataclass
class IndexObject(ConfigObject):
    """
    Object at index.

    Example:

    .. code-block:: yaml

        tpdos:
          - num: 1
            fields:
              - [system, storage_percent]
              - [system, ram_percent]
            event_timer_ms: 30000
    """

    name: str = ""
    """Name of object, must be in lower_snake_case."""
    index: int = 0
    """Index of object, fw/sw common object are in 0x3000, card objects are in 0x4000."""
    object_type: str = "variable"
    """Object type; must be ``"variable"``, ``"array"``, or ``"record"``."""
    subindexes: list[SubindexObject] = field(default_factory=list)
    """Defines subindexes for records and arrays."""
    generate_subindexes: Optional[GenerateSubindex] = None
    """Used to generate subindexes for arrays."""


@dataclass
class Tpdo:
    """
    TPDO.

    Example:

    .. code-block:: yaml

        tpdos:
          - num: 1
            fields:
              - [system, storage_percent]
              - [system, ram_percent]
            event_timer_ms: 30000
    """

    num: int
    """TPDO number, 1-16."""
    rtr: bool = False
    """TPDO supports RTR."""
    transmission_type: str = "timer"
    """Transmission type of TPDO. Must be ``"timer"`` or ``"sync"``."""
    sync: int = 0
    """Send this TPDO every x SYNCs. 0 for acycle. Max 240."""
    sync_start_value: int = 0
    """
    When set to 0, the count of sync is not process for this TPDO.
    When set to 1, the count of sync is processed for this TPDO .
    """
    event_timer_ms: int = 0
    """Send the TPDO periodicly in milliseconds."""
    inhibit_time_ms: int = 0
    """Delay after boot before the event timer starts in milliseconds."""
    fields: list[list[str]] = field(default_factory=list)
    """Index and subindexes of objects to map to the TPDO."""


@dataclass
class Rpdo:
    """
    RPDO section.

    Example:

    .. code-block:: yaml

        rpdos:
          - num: 1
            card: c3
            tpdo_num: 1
    """

    num: int
    """TPDO number to use, 1-16."""
    card: str
    """Card the TPDO is from."""
    tpdo_num: int
    """TPDO number, 1-16."""


@dataclass
class CardConfig:
    """
    YAML card config.

    Example:

    .. code-block:: yaml

        std_objects:
          - device_type
          - error_register
          ...

        objects:
          - index: 0x3000
            name: satellite_id
          ...

        tpdos:
          - num: 1
            fields:
             - [satellite_id]
          ...

        rpdos:
          - num: 1
            card: c3
            tpdo_num: 1
          ...
    """

    std_objects: list[str] = field(default_factory=list)
    """Standard object to include in OD."""
    objects: list[IndexObject] = field(default_factory=list)
    """Unique card objects."""
    tpdos: list[Tpdo] = field(default_factory=list)
    """TPDOs for the card."""
    rpdos: list[Rpdo] = field(default_factory=list)
    """RPDOs for the card."""
    fram: list[list[str]] = field(default_factory=list)
    """C3 only. List of index and subindex for the c3 to save the values of to F-RAM."""

    @classmethod
    @cache
    def from_yaml(cls, config_path: Path) -> CardConfig:
        """Load a card YAML config file."""

        with config_path.open() as f:
            config_raw = load(f, Loader=CLoader)
        return from_dict(data_class=cls, data=config_raw)
