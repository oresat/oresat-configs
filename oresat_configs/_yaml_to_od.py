from __future__ import annotations

import json
import logging
from copy import deepcopy
from enum import Enum, unique
from pathlib import Path
from typing import Any, Union

import requests
from canopen.objectdictionary import Array, ObjectDictionary, Record, Variable

from .configs.cards_config import CardsConfig
from .configs.mission_config import MissionConfig
from .configs.od_config import (ConfigObject, GenerateSubindex, IndexObject,
                                OdConfig, SubindexObject)
from .std_objs import STD_OBJS

logger = logging.getLogger(__name__)

RPDO_COMM_START = 0x1400
RPDO_PARA_START = 0x1600
TPDO_COMM_START = 0x1800
TPDO_PARA_START = 0x1A00


@unique
class DataType(Enum):
    BOOL = 0x1
    INT8 = 0x2
    INT16 = 0x3
    INT32 = 0x4
    UINT8 = 0x5
    UINT16 = 0x6
    UINT32 = 0x7
    FLOAT32 = 0x8
    STR = 0x9
    OCTET_STR = 0xA
    UNICODE_STR = 0xB
    DOMAIN = 0xF
    FLOAT64 = 0x11
    INT64 = 0x15
    UINT64 = 0x1B

    @property
    def is_int(self) -> bool:
        return self.name.startswith("INT") or self.name.startswith("UINT")

    @property
    def is_float(self) -> bool:
        return self.name.startswith("FLOAT")

    @property
    def size(self) -> int:
        size = 0
        if self.name.endswith("8") or self.name == "BOOL":
            size = 8
        elif self.name.endswith("16"):
            size = 16
        elif self.name.endswith("32"):
            size = 32
        elif self.name.endswith("64"):
            size = 64
        return size

    @property
    def has_dynamic_len(self) -> bool:
        return self.size == 0

    @property
    def default(self) -> bool | int | float | str | bytes | None:
        default: Any = 0
        if self.name == "BOOL":
            default = False
        elif self.name.startswith("FLOAT"):
            default = 0.0
        elif self.name in ["STR", "UNICODE_STR"]:
            default = ""
        elif self.name == "OCTET_STR":
            default = b"\x00"
        elif self.name == "DOMAIN":
            default = None
        return default


def _set_var_default(obj: ConfigObject, var: Variable) -> None:
    default = obj.default
    if obj.data_type == "str" and obj.str_length > 1:
        default = " " * obj.str_length
    elif obj.data_type == "octet_str" and obj.str_length > 1:
        default = b"\x00" * obj.str_length
    elif default is None:
        default = DataType(var.data_type).default
    elif DataType(var.data_type).is_int and isinstance(default, str):
        default = int(default, 16) if default.startswith("0x") else int(default)
    var.default = default


def _parse_bit_definitions(obj: IndexObject | SubindexObject | GenerateSubindex) -> dict[str, list[int]]:
    bit_defs = {}
    for name, bits in obj.bit_definitions.items():
        if isinstance(bits, int):
            bit_defs[name] = [bits]
        elif isinstance(bits, list):
            bit_defs[name] = bits
        elif isinstance(bits, str) and "-" in bits:
            low, high = sorted([int(i) for i in bits.split("-")])
            bit_defs[name] = list(range(low, high + 1))
    return bit_defs


def _make_var(obj: IndexObject | SubindexObject, index: int, subindex: int = 0) -> Variable:
    var = Variable(obj.name, index, subindex)
    var.access_type = obj.access_type
    var.description = obj.description
    var.bit_definitions = _parse_bit_definitions(obj)
    for name, value in obj.value_descriptions.items():
        var.add_value_description(value, name)
    var.unit = obj.unit
    if obj.scale_factor != 1:
        var.factor = obj.scale_factor
    var.data_type = DataType[obj.data_type.upper()].value
    _set_var_default(obj, var)
    if not DataType[obj.data_type.upper()].has_dynamic_len:
        var.pdo_mappable = True
    if obj.value_descriptions:
        var.max = obj.high_limit or max(obj.value_descriptions.values())
        var.min = obj.low_limit or min(obj.value_descriptions.values())
    else:
        var.max = obj.high_limit
        var.min = obj.low_limit
    return var


def _make_rec(obj: IndexObject) -> Record:
    index = obj.index
    rec = Record(obj.name, index)

    var0 = Variable("highest_index_supported", index, 0x0)
    var0.access_type = "const"
    var0.data_type = DataType.UINT8.value
    rec.add_member(var0)

    for sub_obj in obj.subindexes:
        if sub_obj.subindex in rec.subindices:
            raise ValueError(f"subindex 0x{sub_obj.subindex:X} already in record")
        var = _make_var(sub_obj, index, sub_obj.subindex)
        rec.add_member(var)
        var0.default = sub_obj.subindex

    return rec


def _make_arr(obj: IndexObject) -> Array:
    index = obj.index
    arr = Array(obj.name, index)

    var0 = Variable("highest_index_supported", index, 0x0)
    var0.access_type = "const"
    var0.data_type = DataType.UINT8.value
    arr.add_member(var0)

    subindexes = []
    names = []
    gen_sub = obj.generate_subindexes
    if gen_sub is not None:
        subindexes = list(range(1, gen_sub.subindexes + 1))
        names = [f"{gen_sub.name}_{subindex}" for subindex in subindexes]
        for subindex, name in zip(subindexes, names):
            if subindex in arr.subindices:
                raise ValueError(f"subindex 0x{subindex:X} already in array")
            var = Variable(name, index, subindex)
            var.access_type = gen_sub.access_type
            var.data_type = DataType[gen_sub.data_type.upper()].value
            var.bit_definitions = _parse_bit_definitions(gen_sub)
            for name, value in gen_sub.value_descriptions.items():
                var.add_value_description(value, name)
            var.unit = gen_sub.unit
            var.factor = gen_sub.scale_factor
            if obj.value_descriptions:
                var.max = gen_sub.high_limit or max(gen_sub.value_descriptions.values())
                var.min = gen_sub.low_limit or min(gen_sub.value_descriptions.values())
            else:
                var.max = gen_sub.high_limit
                var.min = gen_sub.low_limit
            _set_var_default(gen_sub, var)
            if not DataType[obj.data_type.upper()].has_dynamic_len:
                var.pdo_mappable = True
            arr.add_member(var)
            var0.default = subindex
    else:
        for sub_obj in obj.subindexes:
            if sub_obj.subindex in arr.subindices:
                raise ValueError(f"subindex 0x{sub_obj.subindex:X} already in array")
            var = _make_var(sub_obj, index, sub_obj.subindex)
            arr.add_member(var)
            var0.default = sub_obj.subindex

    return arr


def add_objects(od: ObjectDictionary, objects: list[IndexObject]) -> None:
    """File a objectdictionary with all the objects."""

    for obj in objects:
        if obj.index in od.indices:
            raise ValueError(f"index 0x{obj.index:X} already in OD")

        try:
            if obj.object_type == "variable":
                var = _make_var(obj, obj.index)
                od.add_object(var)
            elif obj.object_type == "record":
                rec = _make_rec(obj)
                od.add_object(rec)
            elif obj.object_type == "array":
                arr = _make_arr(obj)
                od.add_object(arr)
        except Exception as e:
            raise ValueError(f"{od.device_information.product_name} {e}") from e


def _make_pdo_comms_rec(
    name: str,
    pdo_type: str,
    index: int,
    cob_id: int,
    inhibit_time: int,
    transmission_type: int,
    event_timer: int,
    sync_start_value: int,
) -> Record:
    comm_rec = Record(name + "_communication_parameters", index)

    var0 = Variable("highest_index_supported", index, 0)
    var0.access_type = "const"
    var0.data_type = DataType.UINT8.value
    var0.default = 6 if pdo_type == "tpdo" else 5
    comm_rec.add_member(var0)

    var = Variable("cob_id", index, 1)
    var.access_type = "const"
    var.data_type = DataType.UINT32.value
    var.default = cob_id
    comm_rec.add_member(var)

    var = Variable("transmission_type", index, 2)
    var.access_type = "const"
    var.data_type = DataType.UINT8.value
    var.default = transmission_type
    comm_rec.add_member(var)

    if pdo_type == "tpdo":
        var = Variable("inhibit_time", index, 3)
        var.access_type = "const"
        var.data_type = DataType.UINT16.value
        var.default = inhibit_time
        var.unit = "ms"
        comm_rec.add_member(var)

    var = Variable("event_timer", index, 5)
    var.access_type = "const"
    var.data_type = DataType.UINT16.value
    var.default = event_timer
    var.unit = "ms"
    comm_rec.add_member(var)

    if pdo_type == "tpdo":
        var = Variable("sync_start_value", index, 6)
        var.access_type = "const"
        var.data_type = DataType.UINT8.value
        var.default = sync_start_value
        comm_rec.add_member(var)

    return comm_rec


def add_pdo_objs(od: ObjectDictionary, config: OdConfig, pdo_type: str) -> None:
    """Add tpdo objects to OD."""

    if pdo_type == "tpdo":
        pdos = config.tpdos
        comms_start = TPDO_COMM_START
        map_start = TPDO_PARA_START
    elif pdo_type == "rpdo":
        pdos = config.rpdos
        comms_start = RPDO_COMM_START
        map_start = RPDO_PARA_START
    else:
        raise ValueError(f"invalid pdo value of {pdo_type}")

    for pdo in pdos:
        if pdo_type == "tpdo":
            od.device_information.nr_of_TXPDO += 1
        else:
            od.device_information.nr_of_RXPDO += 1

        comm_index = comms_start + pdo.num - 1
        map_index = map_start + pdo.num - 1
        comm_rec = Record(f"{pdo_type}_{pdo.num}_communication_parameters", comm_index)
        map_rec = Record(f"{pdo_type}_{pdo.num}_mapping_parameters", map_index)
        od.add_object(map_rec)
        od.add_object(comm_rec)

        # index 0 for mapping index
        var0 = Variable("highest_index_supported", map_index, 0x0)
        var0.access_type = "const"
        var0.data_type = DataType.UINT8.value
        map_rec.add_member(var0)

        for p_field in pdo.fields:
            subindex = pdo.fields.index(p_field) + 1
            var = Variable(f"mapping_object_{subindex}", map_index, subindex)
            var.access_type = "const"
            var.data_type = DataType.UINT32.value
            if len(p_field) == 1:
                mapped_obj = od[p_field[0]]
            elif len(p_field) == 2:
                mapped_obj = od[p_field[0]][p_field[1]]
            else:
                raise ValueError(f"{pdo_type} field must be a 1 or 2 values")
            mapped_subindex = mapped_obj.subindex
            value = mapped_obj.index << 16
            value += mapped_subindex << 8
            value += DataType(mapped_obj.data_type).size
            var.default = value
            map_rec.add_member(var)

        var0.default = len(map_rec) - 1

        name = f"{pdo_type}_{pdo.num}"
        if pdo.cob_id == 0:
            cob_id_offset = 0x180 if pdo_type == "tpdo" else 0x200
            cob_id = (((pdo.num - 1) % 4) * 0x100) + ((pdo.num - 1) // 4) + cob_id_offset
        else:
            cob_id = pdo.cob_id
        if pdo_type == "tpdo":
            cob_id |= 1 << 30  # no RTR
        transmission_type = pdo.sync if pdo.transmission_type == "sync" else 254
        inhibit_time = pdo.inhibit_time_ms if pdo_type == "tpdo" else 0
        sync_start_value = pdo.sync_start_value if pdo_type == "tpdo" else 0
        comm_rec = _make_pdo_comms_rec(
            name,
            pdo_type,
            comm_index,
            cob_id,
            inhibit_time,
            transmission_type,
            pdo.event_timer_ms,
            sync_start_value,
        )
        od.add_object(comm_rec)


def add_other_node_pdo_objs(
    od: ObjectDictionary,
    pdo_num: int,
    pdo_node_name: str,
    pdo_node_od: ObjectDictionary,
    pdo_type: str,
) -> None:

    if pdo_type == "tpdo":
        pdo_comm_index = RPDO_COMM_START + pdo_num - 1
        pdo_mapping_index = RPDO_PARA_START + pdo_num - 1
        comms_start = TPDO_COMM_START
        para_start = TPDO_PARA_START
        pdo_base_index = 0x5100
        mapped_name = f"{pdo_node_name}_control"
    elif pdo_type == "rpdo":
        pdo_comm_index = TPDO_COMM_START + pdo_num - 1
        pdo_mapping_index = TPDO_PARA_START + pdo_num - 1
        comms_start = RPDO_COMM_START
        para_start = RPDO_PARA_START
        pdo_base_index = 0x5000
        mapped_name = pdo_node_name
    else:
        raise ValueError(f"invalid pdo value of {pdo_type}")

    mapped_index = pdo_base_index + pdo_node_od.node_id
    if mapped_index not in od:
        mapped_rec = Record(mapped_name, mapped_index)
        mapped_rec.description = f"{pdo_node_name} {pdo_type} {pdo_num} mapped data"
        od.add_object(mapped_rec)

        # index 0 for node data index
        var = Variable("highest_index_supported", mapped_index, 0x0)
        var.access_type = "const"
        var.data_type = DataType.UINT8.value
        var.default = 0
        mapped_rec.add_member(var)
    else:
        mapped_rec = od[mapped_index]

    if pdo_type == "rpdo":
        od.device_information.nr_of_RXPDO += 1
    else:
        od.device_information.nr_of_TXPDO += 1
    num = len([i for i in od.indices if comms_start + 16 <= i < para_start]) + 1

    name = f"{pdo_node_name}_{pdo_type}_{pdo_num}"
    comm_index = comms_start + num + 16 - 1
    cob_id = pdo_node_od[pdo_comm_index][0x1].default
    comm_rec = _make_pdo_comms_rec(name, pdo_type, comm_index, cob_id, 0, 254, 0, 0)
    od.add_object(comm_rec)

    mapping_index = para_start + num + 16 - 1
    mapping_rec = Record(f"{pdo_node_name}_{pdo_type}_{pdo_num}_mapping_parameters", mapping_index)
    od.add_object(mapping_rec)

    # index 0 for map index
    var = Variable("highest_index_supported", mapping_index, 0x0)
    var.access_type = "const"
    var.data_type = DataType.UINT8.value
    var.default = 0
    mapping_rec.add_member(var)

    for j in range(len(pdo_node_od[pdo_mapping_index])):
        if j == 0:
            continue  # skip

        pdo_mapping_obj = pdo_node_od[pdo_mapping_index][j]

        mapped_subindex = mapped_rec[0].default + 1
        pdo_mapped_index = (pdo_mapping_obj.default >> 16) & 0xFFFF
        pdo_mapped_subindex = (pdo_mapping_obj.default >> 8) & 0xFF
        if isinstance(pdo_node_od[pdo_mapped_index], Variable):
            pdo_mapped_obj = pdo_node_od[pdo_mapped_index]
            name = pdo_mapped_obj.name
        else:
            pdo_mapped_obj = pdo_node_od[pdo_mapped_index][pdo_mapped_subindex]
            name = pdo_node_od[pdo_mapped_index].name + "_" + pdo_mapped_obj.name
        var = Variable(name, mapped_index, mapped_subindex)
        var.description = pdo_mapped_obj.description
        var.access_type = "rw"
        var.data_type = pdo_mapped_obj.data_type
        var.default = pdo_mapped_obj.default
        var.unit = pdo_mapped_obj.unit
        var.factor = pdo_mapped_obj.factor
        var.bit_definitions = deepcopy(pdo_mapped_obj.bit_definitions)
        var.value_descriptions = deepcopy(pdo_mapped_obj.value_descriptions)
        var.max = pdo_mapped_obj.max
        var.min = pdo_mapped_obj.min
        var.pdo_mappable = True
        mapped_rec.add_member(var)

        # manager node mapping obj
        mapping_subindex = mapping_rec[0].default + 1
        var = Variable(f"mapping_object_{mapping_subindex}", mapping_index, mapping_subindex)
        var.access_type = "const"
        var.data_type = DataType.UINT32.value
        value = mapped_index << 16
        value += mapped_subindex << 8
        if mapped_subindex == 0:
            mapped_obj = od[mapped_index]
        else:
            mapped_obj = od[mapped_index][mapped_subindex]
        value += DataType(mapped_obj.data_type).size
        var.default = value
        mapping_rec.add_member(var)

        mapped_rec[0].default += 1
        mapping_rec[0].default += 1


def add_std_objects(od: ObjectDictionary, od_config: OdConfig):
    std_objs = {obj.name: obj for obj in STD_OBJS}
    for obj_name in od_config.std_objects:
        obj = std_objs[obj_name]
        if obj.object_type == "variable":
            od.add_object(_make_var(obj, obj.index))
        elif obj.object_type == "record":
            od.add_object(_make_rec(obj))
        elif obj.object_type == "array":
            od.add_object(_make_arr(obj))


def gen_od(configs: Union[OdConfig, list[OdConfig]]) -> ObjectDictionary:
    if isinstance(configs, OdConfig):
        configs = [configs]

    od = ObjectDictionary()
    od.bitrate = 1_000_000  # bps
    od.node_id = 0
    od.device_information.allowed_baudrates = set([1000])  # kpbs
    od.device_information.vendor_name = "PSAS"
    od.device_information.vendor_number = 0
    od.device_information.product_name = configs[0].name
    od.device_information.product_number = 0
    od.device_information.revision_number = 0
    od.device_information.order_code = 0
    od.device_information.simple_boot_up_manager = False
    od.device_information.simple_boot_up_slave = False
    od.device_information.granularity = 8
    od.device_information.dynamic_channels_supported = False
    od.device_information.group_messaging = False
    od.device_information.nr_of_RXPDO = 0
    od.device_information.nr_of_TXPDO = 0
    od.device_information.LSS_supported = False

    for config in configs:
        add_std_objects(od, config)
        add_objects(od, config.objects)
        add_pdo_objs(od, config, "tpdo")
        add_pdo_objs(od, config, "rpdo")

    # set all object values to its default value
    for index in od:
        if not isinstance(od[index], Variable):
            for subindex in od[index]:
                od[index][subindex].value = od[index][subindex].default
        else:
            od[index].value = od[index].default

    return od


def gen_manager_od(config: OdConfig, od_db: dict[str, ObjectDictionary]) -> ObjectDictionary:
    od = gen_od([config])
    for node_name, node_od in od_db.items():
        for tpdo_num in range(16):
            index = TPDO_COMM_START + tpdo_num - 1
            if index in node_od.indices:
                add_other_node_pdo_objs(od, tpdo_num, node_name, node_od, "rpdo")
        for rpdo_num in range(1, node_od.device_information.nr_of_RXPDO + 1):
            index = TPDO_COMM_START + tpdo_num - 1
            if index in node_od.indices:
                add_other_node_pdo_objs(od, rpdo_num, node_name, node_od, "tpdo")

    # set all object values to its default value
    for index in od:
        if not isinstance(od[index], Variable):
            for subindex in od[index]:
                od[index][subindex].value = od[index][subindex].default
        else:
            od[index].value = od[index].default

    return od


def set_od_node_id(od: ObjectDictionary, node_id: int):
    od.node_id = node_id
    if 0x1014 in od:
        od[0x1014].default = 0x80 + node_id
        od[0x1014].value = 0x80 + node_id
    cob_id_sub = 1
    for i in range(16):
        # RPDO
        cob_id = ((i % 4) * 0x100) + (i // 4) + 0x200
        index = RPDO_COMM_START + i
        if index in od.indices and (od[index][cob_id_sub].value & 0x7FF) == cob_id:
            od[index][cob_id_sub].default += node_id
            od[index][cob_id_sub].value += node_id
        # TPDO
        cob_id = ((i % 4) * 0x100) + (i // 4) + 0x180
        index = TPDO_COMM_START + i
        if index in od.indices and (od[index][cob_id_sub].value & 0x7FF) == cob_id:
            od[index][cob_id_sub].default += node_id
            od[index][cob_id_sub].value += node_id


def load_od_configs(cards_config: CardsConfig, config_dir: Path, force_download: bool = False) -> dict[str, OdConfig]:
    cache_dir = Path("~/.cache/oresat-configs").expanduser()
    data_json_path = cache_dir / "data.json"

    if not cache_dir.is_dir():
        cache_dir.mkdir(parents=True)

    data = {}
    if not force_download and data_json_path.is_file():
        try:
            with data_json_path.open("r") as f:
                data = json.load(f)
        except json.decoder.JSONDecodeError:
            pass

    od_configs = {}
    for config_info in cards_config.configs:
        if config_info.od_source.startswith("http"):
            config_path = cache_dir / f"{config_info.name}.yaml"
            if config_info.od_source != data.get(config_info.name, "") or not config_path.is_file():
                logger.info("downloading %s", config_info.od_source)
                r = requests.get(config_info.od_source, timeout=1)
                with config_path.open("w") as f:
                    f.write(r.text)
        else:
            config_path = config_dir / config_info.od_source

        data[config_info.name] = config_info.od_source
        od_configs[config_info.name] = OdConfig.from_yaml(config_path)

    with data_json_path.open("w") as f:
        json.dump(data, f, indent=4)

    return od_configs


def load_od_db(
    cards_config: CardsConfig, od_configs: dict[str, OdConfig]
) -> dict[str, ObjectDictionary]:
    od_db = {}

    for card_info in cards_config.cards:
        tmp = []
        if card_info.base:
            tmp.append(od_configs[card_info.base])
        if card_info.common:
            tmp.append(od_configs[card_info.common])
        if len(tmp) == 0:
            continue
        od = gen_od(tmp)
        set_od_node_id(od, card_info.node_id)
        od_db[card_info.name] = od

    manager_info = cards_config.manager
    c3_od = gen_manager_od(od_configs[manager_info.base], od_db)
    set_od_node_id(c3_od, manager_info.node_id)
    od_db[manager_info.name] = c3_od

    return od_db


def get_objs(od: ObjectDictionary, fields: list[list[str]]) -> list[Variable]:
    objs = []
    for names in fields:
        if len(names) == 1:
            objs.append(od[names[0]])
        elif len(names) == 2:
            objs.append(od[names[0]][names[1]])
    return objs


def get_beacon_def(od: ObjectDictionary, mission_config: MissionConfig) -> list[Variable]:
    return get_objs(od, mission_config.beacon.fields)

def get_fram_def(od: ObjectDictionary, od_config: OdConfig) -> list[Variable]:
    return get_objs(od, od_config.fram)
