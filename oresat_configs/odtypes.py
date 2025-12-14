from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from canopen.objectdictionary import (
    UNSIGNED8,
    UNSIGNED16,
    UNSIGNED32,
    ODArray,
    ODRecord,
    ODVariable,
)


class HighestSubindexSupported(ODVariable):
    '''Highest subindex supported in a particular complex data type.

    Intended to be placed at sub-index 0 of records and arrays. The standard indicates that some
    amount of discovery may be enabled by this by attempting to read subindex 0 of an arbitrary
    entry and either it will SDO abort for variables or return the number of valid sub-entries that
    can be read.

    Because the value depends on the entry it's being added to it is recommended to add this after
    adding all other members:
    >>> entry.add_member(HighestSubindexSupported(entry))

    See CiA-301:
    - 7.4.7.1 - Description of this variable.
    - 7.4.7.{1,3,4,5,6) - Default complex types this is used in.
    - 7.4.7.2 - Not technically this type but very similar.
    '''

    def __init__(self, entry: ODArray | ODRecord) -> None:
        # FIXME: should be "highest_subindex_supported" but isn't for backward compatibility
        super().__init__("highest_index_supported", entry.index, 0x0)
        self.access_type = "const"
        self.data_type = UNSIGNED8
        self.default = max(entry) if len(entry) else 0


class COBId(ODVariable):
    '''COB-ID (Communication Object ID).

    A COB-ID is a CAN-ID with two extra bits of information, associated with a specific COB. Not
    every COBhas the same interpretation of the extra top two bits, consult the spec for meaning.
    Note that many are active-low.

    See CiA-301:
    - 7.2: Definition of COBs
    - 7.5.2.5:  SYNC
    - 7.5.2.15: TIME
    - 7.5.2.17: EMCY
    - 7.5.2.31: EMCY consumer
    - 7.5.2.33: SDO server
    - 7.5.2.33: SDO client
    - 7.5.2.35: RPDO
    - 7.5.2.37: TPDO
    '''

    def __init__(self, index: int, subindex: int, cob_id: int) -> None:
        super().__init__("cob_id", index, subindex)
        self.access_type = "const"
        self.data_type = UNSIGNED32
        self.default = cob_id

    @staticmethod
    def pdo(node_id: int, num: int) -> int:
        # CANopen defines a generic pre-defined connection set of 4 TX and RX PDOs per device and
        # then also allows for application specific pre-defined connections. We decided to not use
        # the application specific connections and instead assign 4 consecutive node ids to each
        # node meaning that we can define up to 16 generic PDOs per node instead. I'm unsure of the
        # reason why we deviated in such a way.
        return node_id + (((num - 1) % 4) * 0x100) + ((num - 1) // 4) + 0x180

    def bit_31(self, *, from_default: bool = False) -> bool:
        val = self.default if from_default else self.value

        if val is None:
            raise TypeError("COBId not initialized")
        return bool(val & 1 << 31)

    def bit_30(self, *, from_default: bool = False) -> bool:
        val = self.default if from_default else self.value

        if val is None:
            raise TypeError("COBId not initialized")
        return bool(val & 1 << 30)

    def can_id(self, *, from_default: bool = False) -> int:
        val = self.default if from_default else self.value

        if val is None:
            raise TypeError("COBId not initialized")
        if val & 1 << 29:
            return val & 0x7FFFFFF
        return val & 0x7FF


@dataclass
class PDOSync:
    sync: int
    start: int

    def __post_init__(self) -> None:
        if not (0 <= self.sync <= 240):
            raise ValueError(f"Invalid PDOSync sync {self.sync}")
        if not (0 <= self.start <= 240):
            raise ValueError(f"Invalid PDOSync start {self.start}")


@dataclass
class PDOTimer:
    inhibit: int | None
    timer: int | None

    def __post_init__(self) -> None:
        if self.inhibit is not None and self.inhibit < 0:
            raise ValueError(f"Invalid PDOTimer inhibit {self.inhibit}")
        if self.timer is not None and self.timer < 0:
            raise ValueError(f"Invalid PDOTimer timer {self.timer}")


class PDOCommunicationParameter(ODRecord):
    '''The pre-defined DEFSTRUCT PDO_COMMUNICATON_PARAMETER.

    Communication parameters describe when the associated PDO is transmitted.

    See CiA-301:
    - 7.4.7.1: List of pre-define data types
    - 7.4.8.1: PDO communication parameter record layout
    - 7.5.2.35: RPDO communication parameter value definitions
    - 7.5.2.37: TPDO communication parameter value definitions
    '''

    INDEX_BASE: Final[dict[Literal['tpdo', 'rpdo'], int]] = {
        'rpdo': 0x1400,
        'tpdo': 0x1800,
    }

    def __init__(
        self,
        kind: Literal['tpdo', 'rpdo'],
        num: int,
        cob_id: int,
        transmission: PDOSync | PDOTimer,
    ) -> None:
        index = self.INDEX_BASE[kind] + num - 1
        super().__init__(f"{kind}_{num}_communication_parameters", index)

        self.add_member(COBId(index, 0x1, cob_id))

        var = ODVariable("transmission_type", index, 0x2)
        var.access_type = "const"
        var.data_type = UNSIGNED8
        if isinstance(transmission, PDOSync):
            var.default = transmission.sync
        else:
            var.default = 0xFE  # event driven
        self.add_member(var)

        # FIXME: the following are all optional entries and should be omitted when the relevant
        #        values are None or of the wrong type but are kept for now for backwards
        #        compatibility.
        if isinstance(transmission, PDOTimer) and transmission.inhibit is not None:
            var = ODVariable("inhibit_time", index, 0x3)
            var.access_type = "const"
            var.data_type = UNSIGNED16
            var.default = transmission.inhibit
            self.add_member(var)

        # subindex 4 is reserved

        if isinstance(transmission, PDOTimer):
            var = ODVariable("event_timer", index, 0x5)
            var.access_type = "rw" if kind == 'tpdo' else 'const'
            var.data_type = UNSIGNED16
            var.default = transmission.timer if transmission.timer is not None else 0
            self.add_member(var)

        if isinstance(transmission, PDOSync):
            var = ODVariable("sync_start_value", index, 0x6)
            var.access_type = "const"
            var.data_type = UNSIGNED8
            var.default = transmission.start
        elif isinstance(transmission, PDOTimer) and transmission.timer is not None:
            var = ODVariable("sync_start_value", index, 0x6)
            var.access_type = "const"
            var.data_type = UNSIGNED8
            var.default = 0
        self.add_member(var)

        self.add_member(HighestSubindexSupported(self))


class PDOMappedObject(ODVariable):
    '''A single PDO Mapping.

    An entry of a PDOMappingParameter pointing to the object in the ObjectDictionary that this PDO
    is associated with.

    See CiA-301:
    - 7.5.2.36: RPDOs
    - 7.5.2.38: TPDOs
    '''

    def __init__(self, index: int, subindex: int, mapped: ODVariable) -> None:
        super().__init__(f"mapping_object_{subindex}", index, subindex)
        self.access_type = "const"
        self.data_type = UNSIGNED32
        self.default = mapped.index << 16 | mapped.subindex << 8 | len(mapped)

    def mapped_index(self, *, from_default: bool = False) -> int:
        val = self.default if from_default else self.value

        if val is None:
            raise TypeError("PDOMappedObject not initialized")
        return val >> 16 & 0xFFFF

    def mapped_subindex(self, *, from_default: bool = False) -> int:
        val = self.default if from_default else self.value

        if val is None:
            raise TypeError("PDOMappedObject not initialized")
        return val >> 8 & 0xFF

    def mapped_length(self, *, from_default: bool = False) -> int:
        val = self.default if from_default else self.value

        if val is None:
            raise TypeError("PDOMappedObject not initialized")
        return val & 0xFF


class PDOMappingParameter(ODRecord):
    '''PDO Mapping parameters.

    A table for a PDO that maps that PDO with the related objects in the ObjectDictionary. Every
    PDO should have all entries exist somewhere in the ObjectDictionary.

    See CiA-301:
    - 7.5.2.36: RPDOs
    - 7.5.2.38: TPDOs
    '''

    INDEX_BASE: Final[dict[Literal['tpdo', 'rpdo'], int]] = {
        'rpdo': 0x1600,
        'tpdo': 0x1A00,
    }

    def __init__(self, kind: Literal['tpdo', 'rpdo'], num: int, objects: list[ODVariable]) -> None:
        index = self.INDEX_BASE[kind] + num - 1
        super().__init__(f"{kind}_{num}_mapping_parameters", index)
        for subindex, mapped in enumerate(objects, start=1):
            self.add_member(PDOMappedObject(index, subindex, mapped))

        self.add_member(HighestSubindexSupported(self))
