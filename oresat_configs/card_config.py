"""Load a card config file."""

# dacite doesn't work with | from __future__.annotations on 3.9, remove when upgrading to 3.10+
# ruff: noqa: UP007, UP045
from __future__ import annotations

from collections.abc import Mapping  # noqa: TC003 dacite uses type information at runtime
from dataclasses import dataclass, field
from itertools import chain
from typing import TYPE_CHECKING, Literal, NamedTuple, Optional, Union, cast

from .odtypes import (
    COBId,
    HighestSubindexSupported,
    PDOCommunicationParameter,
    PDOMappingParameter,
    PDOSync,
    PDOTimer,
)

if TYPE_CHECKING:
    from pathlib import Path

from canopen.objectdictionary import (
    BOOLEAN,
    DATA_TYPES,
    DOMAIN,
    INTEGER8,
    INTEGER16,
    INTEGER32,
    INTEGER64,
    OCTET_STRING,
    REAL32,
    REAL64,
    UNSIGNED8,
    UNSIGNED16,
    UNSIGNED32,
    UNSIGNED64,
    VISIBLE_STRING,
    ObjectDictionary,
    ODArray,
    ODRecord,
    ODVariable,
)
from dacite import Config, from_dict
from yaml import CLoader, load

DataType = Literal[
    'bool',
    'int8',
    'int16',
    'int32',
    'int64',
    'uint8',
    'uint16',
    'uint32',
    'uint64',
    'float32',
    'float64',
    'str',
    'octet_str',
    'domain',
]


class DataTypeDefault(NamedTuple):
    od_type: int
    default: bool | int | float | str | bytes | None
    size: int
    low_limit: int | None
    high_limit: int | None


DATA_TYPE_DEFAULTS = {
    'bool': DataTypeDefault(BOOLEAN, False, 8, None, None),  # noqa: FBT003
    'int8': DataTypeDefault(INTEGER8, 0, 8, -(2**7), 2**7 - 1),
    'int16': DataTypeDefault(INTEGER16, 0, 16, -(2**15), 2**15 - 1),
    'int32': DataTypeDefault(INTEGER32, 0, 32, -(2**31), 2**31 - 1),
    'int64': DataTypeDefault(INTEGER64, 0, 64, -(2**63), 2**63 - 1),
    'uint8': DataTypeDefault(UNSIGNED8, 0, 8, 0, 2**8 - 1),
    'uint16': DataTypeDefault(UNSIGNED16, 0, 16, 0, 2**16 - 1),
    'uint32': DataTypeDefault(UNSIGNED32, 0, 32, 0, 2**32 - 1),
    'uint64': DataTypeDefault(UNSIGNED64, 0, 64, 0, 2**64 - 1),
    'float32': DataTypeDefault(REAL32, 0.0, 32, None, None),
    'float64': DataTypeDefault(REAL64, 0.0, 64, None, None),
    'str': DataTypeDefault(VISIBLE_STRING, "", 0, None, None),
    'octet_str': DataTypeDefault(OCTET_STRING, b"", 0, None, None),
    'domain': DataTypeDefault(DOMAIN, None, 0, None, None),
}


@dataclass
class ConfigObject:
    """Object in config."""

    name: str = ""
    """Name of object, must be in lower_snake_case."""
    data_type: DataType = "domain"
    """Data type of the object."""
    length: int = 1
    """Length of an octet string object (only used when `data_type` is set to ``"octet_str"``)."""
    access_type: Literal['rw', 'ro', 'wo', 'const'] = "rw"
    """
    Access type of object over the CAN bus, can be ``"rw"``, ``"ro"``, ``"wo"``, or ``"const"``.
    """
    default: Union[bool, int, float, str, bytes, None] = None
    """Default value of object."""
    description: str = ""
    """Description of object."""
    value_descriptions: dict[str, int] = field(default_factory=dict)
    """Optional: Can be used to define enum values for an unsigned integer data types."""
    bit_definitions: Mapping[str, Union[int, str, list[int]]] = field(default_factory=dict)
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

    def __post_init__(self) -> None:
        # Because self.bit_definitions values are a union the type checker can't reason that we
        # later fixed all the values to be just list[int]. This local helps the type checker later
        # on when we use it assuming just list[int].
        bit_definitions: dict[str, list[int]] = {}
        for name, bits in self.bit_definitions.items():
            if isinstance(bits, int):
                bit_definitions[name] = [bits]
            elif isinstance(bits, str) and "-" in bits:
                low, high = sorted(int(i) for i in bits.split("-"))
                bit_definitions[name] = list(range(low, high + 1))
            elif isinstance(bits, list):
                bit_definitions[name] = bits  # Already in correct format
            else:
                raise TypeError(f'Invalid bitdef {name}:{bits}')

        bits = list(chain.from_iterable(bit_definitions.values()))
        if len(bits) != len(set(bits)):
            raise ValueError(f"{self.name} bit definitions overlap")

        if self.value_descriptions and self.bit_definitions:
            raise ValueError(f"{self.name} must not have both value descriptions and bit defs")

        if self.value_descriptions and self.data_type in ('str', 'octet_str', 'domain'):
            raise TypeError(
                f"{self.name} Value descriptions given for invalid type {self.data_type}"
            )

        if self.bit_definitions and self.data_type not in ('uint8', 'uint16', 'uint32', 'uint64'):
            raise TypeError(f"{self.name} Bit definitions given for invalid type {self.data_type}")

        if self.low_limit is None:
            if self.value_descriptions:
                self.low_limit = min(self.value_descriptions.values())
            else:
                self.low_limit = DATA_TYPE_DEFAULTS[self.data_type].low_limit

        if self.high_limit is None:
            if self.value_descriptions:
                self.high_limit = max(self.value_descriptions.values())
            else:
                self.high_limit = DATA_TYPE_DEFAULTS[self.data_type].high_limit

        if self.data_type == 'octet_str':
            self.default = bytes(self.length)
        elif self.default is None:
            self.default = DATA_TYPE_DEFAULTS[self.data_type].default

        if self.value_descriptions and self.default not in self.value_descriptions.values():
            raise ValueError(
                f"{self.name} default value {self.default!r} not in value descriptions"
            )

        if self.data_type in ('str', 'octet_str', 'domain'):
            if self.low_limit is not None:
                raise ValueError(f"{self.name} Low limit set on type that doesn't support it")
            if self.high_limit is not None:
                raise ValueError(f"{self.name} High limit set on type that doesn't support it")

        default_low = DATA_TYPE_DEFAULTS[self.data_type].low_limit
        if self.low_limit is not None and default_low is not None:
            if default_low > self.low_limit:
                raise ValueError(f"{self.name} Low limit too small for type")
            if self.default is None or isinstance(self.default, (str, bytes, bool)):
                raise TypeError(f"{self.name} Default value invalid type {type(self.default)}")
            if self.default < self.low_limit:
                raise ValueError(
                    f"{self.name} Default value {self.default} below low limit {self.low_limit}"
                )

        default_high = DATA_TYPE_DEFAULTS[self.data_type].high_limit
        if self.high_limit is not None and default_high is not None:
            if default_high < self.high_limit:
                raise ValueError(f"{self.name} High limit too big for {self.data_type}")
            if self.default is None or isinstance(self.default, (str, bytes, bool)):
                raise TypeError(f"{self.name} Default value invalid type {type(self.default)}")
            if self.default > self.high_limit:
                raise ValueError(
                    f"{self.name} Default value {self.default} above high limit {self.high_limit}"
                )
            if bit_definitions:
                max_val = sum(2**n for n in chain.from_iterable(bit_definitions.values()))
                if max_val > self.high_limit:
                    raise ValueError(
                        f"{self.name} type {self.data_type} unable to contain bit defs"
                    )
        self.bit_definitions = bit_definitions

    def _to_variable(self, index: int, subindex: int = 0, name: str = '') -> ODVariable:
        var = ODVariable(name or self.name, index, subindex)
        var.unit = self.unit
        var.factor = self.scale_factor
        var.data_type = DATA_TYPE_DEFAULTS[self.data_type].od_type
        for descr, value in self.value_descriptions.items():
            var.add_value_description(value, descr)
        for descr, bits in self.bit_definitions.items():
            if not isinstance(bits, list):
                raise TypeError("__post_init__ bit conversion didn't convert correctly")
            var.add_bit_definition(descr, bits)
        var.min = self.low_limit
        var.max = self.high_limit

        # FIXME: canopen is still working out the type annotations for their codebase. var.default
        #        should be Union[bool, int, float, str, bytes, None] but is only Optional[int].
        #        Remove cast when they fix it upstream.
        var.default = cast(int, self.default)
        var.access_type = self.access_type
        var.description = self.description
        if var.data_type in DATA_TYPES:
            var.pdo_mappable = False
        else:
            var.pdo_mappable = True

        #: Is the default value relative to the node-ID (only applies to COB-IDs)
        # self.relative = False
        #: Storage location of index
        # self.storage_location = None
        return var


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

    subindexes: Optional[Literal['fixed_length', 'node_ids']] = None
    """Subindexes of objects to generate."""

    def _to_subindex(self, name: str, subindex: int) -> SubindexObject:
        return SubindexObject(
            name=name,
            data_type=self.data_type,
            length=1,
            access_type=self.access_type,
            default=self.default,
            description=self.description,
            value_descriptions=self.value_descriptions,
            bit_definitions=self.bit_definitions,
            unit=self.unit,
            scale_factor=self.scale_factor,
            low_limit=self.low_limit,
            high_limit=self.high_limit,
            subindex=subindex,
        )

    def to_subindexes(self, node_ids: dict[str, int]) -> list[SubindexObject]:
        if self.subindexes == 'fixed_length':
            return [
                self._to_subindex(f'{self.name}_{sub}', sub) for sub in range(1, self.length + 1)
            ]

        if self.subindexes == 'node_ids':
            return [self._to_subindex(name, node) for name, node in node_ids.items() if node != 0]

        raise ValueError(f"Invalid subindexes {self.subindexes}")


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

    subindex: int = 0
    """
    Subindex of object, start at subindex 1 (subindex 0 aka highest_index_supported will be
    generated).
    """

    def to_entry(self, index: int) -> ODVariable:
        return self._to_variable(index, self.subindex)


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

    index: int = 0
    """Index of object, fw/sw common object are in 0x3000, card objects are in 0x4000."""
    object_type: Literal['variable', 'array', 'record'] = "variable"
    """Object type; must be ``"variable"``, ``"array"``, or ``"record"``."""
    subindexes: list[SubindexObject] = field(default_factory=list)
    """Defines subindexes for records and arrays."""
    generate_subindexes: Optional[GenerateSubindex] = None
    """Used to generate subindexes for arrays."""

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.generate_subindexes is not None and self.subindexes:
            raise ValueError("IndexObject {self.index} has both subindexes and generate_subindexes")
        if self.object_type == 'variable' and (self.subindexes or self.generate_subindexes):
            raise ValueError("IndexObject {self.index} of type variable must not have subindexes")

    def expand_subindexes(self, node_ids: dict[str, int]) -> None:
        if self.generate_subindexes is None:
            return
        self.subindexes = self.generate_subindexes.to_subindexes(node_ids)
        self.generate_subindexes = None

    def to_entry(self) -> Union[ODArray, ODRecord, ODVariable]:
        if self.object_type == 'variable':
            if self.subindexes:
                raise ValueError("Variable object has subindexes")
            if self.generate_subindexes:
                raise ValueError("Variable object has generate_subindexes")
            return self._to_variable(self.index)

        if self.object_type == 'array':
            if self.subindexes and self.generate_subindexes:
                raise ValueError("Array object must have either subindexes or generate_subindexes")
            if not self.subindexes and not self.generate_subindexes:
                raise ValueError("Array object must have either subindexes or generate_subindexes")
            return self._to_array()

        if self.object_type == 'record':
            if self.generate_subindexes:
                raise ValueError("Record object must not have generate_subindexes")
            return self._to_record()

        raise ValueError(f"Invalid object type {self.object_type}")

    def _to_array(self) -> ODArray:
        arr = ODArray(self.name, self.index)
        arr.description = self.description
        for subindex in self.subindexes:
            arr.add_member(subindex.to_entry(self.index))
        if self.generate_subindexes:
            raise RuntimeError("generate() must be called first")
        arr.add_member(HighestSubindexSupported(arr))
        return arr

    def _to_record(self) -> ODRecord:
        rec = ODRecord(self.name, self.index)
        rec.description = self.description
        for subindex in self.subindexes:
            rec.add_member(subindex.to_entry(self.index))
        rec.add_member(HighestSubindexSupported(rec))
        return rec

    @classmethod
    def from_dict(cls, data: dict) -> IndexObject:
        return from_dict(data_class=cls, data=data, config=Config(strict=True))


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
    transmission_type: Literal['timer', 'sync'] = "timer"
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

    def to_mapping_parameter(self, od: ObjectDictionary) -> ODRecord:
        objects = []
        for name in self.fields:
            obj = od[name[0]]
            if isinstance(obj, (ODRecord, ODArray)):
                assert len(name) == 2
                obj = obj[name[1]]
            else:
                assert len(name) == 1
            objects.append(obj)

        return PDOMappingParameter('tpdo', self.num, objects)

    def to_communication_parameter(self, node_id: int) -> ODRecord:
        transmission: PDOTimer | PDOSync
        if self.transmission_type == 'timer':
            transmission = PDOTimer(self.inhibit_time_ms, self.event_timer_ms)
        else:
            transmission = PDOSync(self.sync, self.sync_start_value)
        return PDOCommunicationParameter(
            'tpdo', self.num, COBId.pdo(node_id, self.num), transmission
        )


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
    fields: list[list[str]] = field(default_factory=list)
    """Index and subindexes of objects to map the RPDO to."""

    def to_mapping_parameter(self, od: ObjectDictionary) -> ODRecord:
        objects = []
        for name in self.fields:
            entry = od[name[0]]
            if isinstance(entry, (ODArray, ODRecord)):
                entry = entry[name[1]]
            objects.append(entry)

        return PDOMappingParameter('rpdo', self.num, objects)

    def to_communication_parameter(self, node_id: int) -> ODRecord:
        cob_id = COBId.pdo(node_id, self.tpdo_num)
        return PDOCommunicationParameter('rpdo', self.num, cob_id, PDOTimer(None, None))


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

    def find_object(self, field: list[str]) -> IndexObject | SubindexObject:
        for obj in self.objects:
            if obj.name == field[0]:
                if obj.object_type == 'variable':
                    return obj
                # else record or array
                for sub in obj.subindexes:
                    if sub.name == field[1]:
                        return sub
        raise ValueError(f'tpdo field {field} not found in config.objects')

    @classmethod
    def from_yaml(cls, config_path: Path) -> CardConfig:
        """Load a card YAML config file."""

        with config_path.open() as f:
            config_raw = load(f, Loader=CLoader)
        return from_dict(data_class=cls, data=config_raw, config=Config(strict=True))
