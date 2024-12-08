"""Convert OreSat configs to ODs."""

from collections import namedtuple
from copy import deepcopy
from importlib import abc, resources
from typing import Union

import canopen
from canopen import ObjectDictionary
from canopen.objectdictionary import Array, Record, Variable
from dacite import from_dict
from yaml import CLoader, load

from . import base
from .beacon_config import BeaconConfig
from .card_config import CardConfig, ConfigObject, IndexObject, SubindexObject
from .card_info import Card
from .constants import Mission, __version__

STD_OBJS_FILE_NAME = resources.files("oresat_configs") / "standard_objects.yaml"

RPDO_COMM_START = 0x1400
RPDO_PARA_START = 0x1600
TPDO_COMM_START = 0x1800
TPDO_PARA_START = 0x1A00

STR_2_OD_DATA_TYPE = {
    "bool": canopen.objectdictionary.BOOLEAN,
    "int8": canopen.objectdictionary.INTEGER8,
    "int16": canopen.objectdictionary.INTEGER16,
    "int32": canopen.objectdictionary.INTEGER32,
    "int64": canopen.objectdictionary.INTEGER64,
    "uint8": canopen.objectdictionary.UNSIGNED8,
    "uint16": canopen.objectdictionary.UNSIGNED16,
    "uint32": canopen.objectdictionary.UNSIGNED32,
    "uint64": canopen.objectdictionary.UNSIGNED64,
    "float32": canopen.objectdictionary.REAL32,
    "float64": canopen.objectdictionary.REAL64,
    "str": canopen.objectdictionary.VISIBLE_STRING,
    "octet_str": canopen.objectdictionary.OCTET_STRING,
    "domain": canopen.objectdictionary.DOMAIN,
}

OdDataTypeInfo = namedtuple("OdDataTypeInfo", ("default", "size", "low_limit", "high_limit"))

OD_DATA_TYPES = {
    canopen.objectdictionary.BOOLEAN: OdDataTypeInfo(False, 8, None, None),
    canopen.objectdictionary.INTEGER8: OdDataTypeInfo(0, 8, -(2**8) // 2, 2**8 // 2 - 1),
    canopen.objectdictionary.INTEGER16: OdDataTypeInfo(0, 16, -(2**16) // 2, 2**16 // 2 - 1),
    canopen.objectdictionary.INTEGER32: OdDataTypeInfo(0, 16, -(2**32) // 2, 2**32 // 2 - 1),
    canopen.objectdictionary.INTEGER64: OdDataTypeInfo(0, 16, -(2**64) // 2, 2**64 // 2 - 1),
    canopen.objectdictionary.UNSIGNED8: OdDataTypeInfo(0, 8, 0, 2**8 - 1),
    canopen.objectdictionary.UNSIGNED16: OdDataTypeInfo(0, 16, 0, 2**16 - 1),
    canopen.objectdictionary.UNSIGNED32: OdDataTypeInfo(0, 32, 0, 2**32 - 1),
    canopen.objectdictionary.UNSIGNED64: OdDataTypeInfo(0, 64, 0, 2**64 - 1),
    canopen.objectdictionary.REAL32: OdDataTypeInfo(0.0, 32, None, None),
    canopen.objectdictionary.REAL64: OdDataTypeInfo(0.0, 64, None, None),
    canopen.objectdictionary.VISIBLE_STRING: OdDataTypeInfo("", 0, None, None),
    canopen.objectdictionary.OCTET_STRING: OdDataTypeInfo(b"", 0, None, None),
    canopen.objectdictionary.DOMAIN: OdDataTypeInfo(None, 0, None, None),
}

DYNAMIC_LEN_DATA_TYPES = [
    canopen.objectdictionary.VISIBLE_STRING,
    canopen.objectdictionary.OCTET_STRING,
    canopen.objectdictionary.DOMAIN,
]


def _set_var_default(obj: ConfigObject, var: Variable) -> None:
    """Set the variables default value based off of configs."""

    default = obj.default
    if obj.data_type == "octet_str":
        default = b"\x00" * obj.length
    elif default is None:
        default = OD_DATA_TYPES[var.data_type].default
    elif var.data_type in canopen.objectdictionary.INTEGER_TYPES and isinstance(default, str):
        # remove node id
        if "+$NODE_ID" in default:
            default = default.split("+")[0]
        elif "$NODE_ID+" in default:
            default = var.default.split("+")[1]

        # convert str to int
        if default.startswith("0x"):
            default = int(default, 16)
        else:
            default = int(default)
    var.default = default


def _parse_bit_definitions(obj: Union[IndexObject, SubindexObject]) -> dict[str, list[int]]:
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


def _make_var(obj: Union[IndexObject, SubindexObject], index: int, subindex: int = 0) -> Variable:
    var = Variable(obj.name, index, subindex)
    var.access_type = obj.access_type
    var.description = obj.description
    var.bit_definitions = _parse_bit_definitions(obj)
    for name, value in obj.value_descriptions.items():
        var.add_value_description(value, name)
    var.unit = obj.unit
    if obj.scale_factor != 1:
        var.factor = obj.scale_factor
    var.data_type = STR_2_OD_DATA_TYPE[obj.data_type]
    _set_var_default(obj, var)
    if var.data_type not in DYNAMIC_LEN_DATA_TYPES:
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
    var0.data_type = canopen.objectdictionary.UNSIGNED8
    rec.add_member(var0)

    for sub_obj in obj.subindexes:
        if sub_obj.subindex in rec.subindices:
            raise ValueError(f"subindex 0x{sub_obj.subindex:X} already in record")
        var = _make_var(sub_obj, index, sub_obj.subindex)
        rec.add_member(var)
        var0.default = sub_obj.subindex

    return rec


def _make_arr(obj: IndexObject, node_ids: dict[str, int]) -> Array:
    index = obj.index
    arr = Array(obj.name, index)

    var0 = Variable("highest_index_supported", index, 0x0)
    var0.access_type = "const"
    var0.data_type = canopen.objectdictionary.UNSIGNED8
    arr.add_member(var0)

    subindexes = []
    names = []
    gen_sub = obj.generate_subindexes
    if gen_sub is not None:
        if gen_sub.subindexes == "fixed_length":
            subindexes = list(range(1, gen_sub.length + 1))
            names = [f"{gen_sub.name}_{subindex}" for subindex in subindexes]
        elif gen_sub.subindexes == "node_ids":
            for name, sub in node_ids.items():
                if sub == 0:
                    continue  # a node_id of 0 is flag for not on can bus
                names.append(name)
                subindexes.append(sub)

        for subindex, name in zip(subindexes, names):
            if subindex in arr.subindices:
                raise ValueError(f"subindex 0x{subindex:X} already in array")
            var = Variable(name, index, subindex)
            var.access_type = gen_sub.access_type
            var.data_type = STR_2_OD_DATA_TYPE[gen_sub.data_type]
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
            if var.data_type not in DYNAMIC_LEN_DATA_TYPES:
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


def _add_objects(
    od: ObjectDictionary, objects: list[IndexObject], node_ids: dict[str, int]
) -> None:
    """File a objectdictionary with all the objects."""

    for obj in objects:
        if obj.index in od.indices:
            raise ValueError(f"index 0x{obj.index:X} already in OD")

        if obj.object_type == "variable":
            var = _make_var(obj, obj.index)
            od.add_object(var)
        elif obj.object_type == "record":
            rec = _make_rec(obj)
            od.add_object(rec)
        elif obj.object_type == "array":
            arr = _make_arr(obj, node_ids)
            od.add_object(arr)


def _add_tpdo_data(od: ObjectDictionary, config: CardConfig) -> None:
    """Add tpdo objects to OD."""

    tpdos = config.tpdos

    for tpdo in tpdos:
        od.device_information.nr_of_TXPDO += 1

        comm_index = TPDO_COMM_START + tpdo.num - 1
        map_index = TPDO_PARA_START + tpdo.num - 1
        comm_rec = Record(f"tpdo_{tpdo.num}_communication_parameters", comm_index)
        map_rec = Record(f"tpdo_{tpdo.num}_mapping_parameters", map_index)
        od.add_object(map_rec)
        od.add_object(comm_rec)

        # index 0 for mapping index
        var0 = Variable("highest_index_supported", map_index, 0x0)
        var0.access_type = "const"
        var0.data_type = canopen.objectdictionary.UNSIGNED8
        map_rec.add_member(var0)

        for t_field in tpdo.fields:
            subindex = tpdo.fields.index(t_field) + 1
            var = Variable(f"mapping_object_{subindex}", map_index, subindex)
            var.access_type = "const"
            var.data_type = canopen.objectdictionary.UNSIGNED32
            if len(t_field) == 1:
                mapped_obj = od[t_field[0]]
            elif len(t_field) == 2:
                mapped_obj = od[t_field[0]][t_field[1]]
            else:
                raise ValueError("tpdo field must be a 1 or 2 values")
            mapped_subindex = mapped_obj.subindex
            value = mapped_obj.index << 16
            value += mapped_subindex << 8
            value += OD_DATA_TYPES[mapped_obj.data_type].size
            var.default = value
            map_rec.add_member(var)

        var0.default = len(map_rec) - 1

        # index 0 for comms index
        var0 = Variable("highest_index_supported", comm_index, 0x0)
        var0.access_type = "const"
        var0.data_type = canopen.objectdictionary.UNSIGNED8
        var0.default = 0x6
        comm_rec.add_member(var0)

        var = Variable("cob_id", comm_index, 0x1)
        var.access_type = "const"
        var.data_type = canopen.objectdictionary.UNSIGNED32
        node_id = od.node_id
        if od.device_information.product_name == "gps" and tpdo.num == 16:
            # time sync TPDO from GPS uses C3 TPDO 1
            node_id = 0x1
            tpdo.num = 1
        var.default = node_id + (((tpdo.num - 1) % 4) * 0x100) + ((tpdo.num - 1) // 4) + 0x180
        if tpdo.rtr:
            var.default |= 1 << 30  # rtr bit, 1 for no RTR allowed
        comm_rec.add_member(var)

        var = Variable("transmission_type", comm_index, 0x2)
        var.access_type = "const"
        var.data_type = canopen.objectdictionary.UNSIGNED8
        if tpdo.transmission_type == "sync":
            var.default = tpdo.sync
        else:
            var.default = 254  # event driven
        comm_rec.add_member(var)

        var = Variable("inhibit_time", comm_index, 0x3)
        var.access_type = "const"
        var.data_type = canopen.objectdictionary.UNSIGNED16
        var.default = tpdo.inhibit_time_ms
        comm_rec.add_member(var)

        var = Variable("event_timer", comm_index, 0x5)
        var.access_type = "rw"
        var.data_type = canopen.objectdictionary.UNSIGNED16
        var.default = tpdo.event_timer_ms
        comm_rec.add_member(var)

        var = Variable("sync_start_value", comm_index, 0x6)
        var.access_type = "const"
        var.data_type = canopen.objectdictionary.UNSIGNED8
        var.default = tpdo.sync_start_value
        comm_rec.add_member(var)


def _add_rpdo_data(
    tpdo_num: int,
    rpdo_node_od: ObjectDictionary,
    tpdo_node_od: ObjectDictionary,
    tpdo_node_name: str,
) -> None:
    tpdo_comm_index = TPDO_COMM_START + tpdo_num - 1
    tpdo_mapping_index = TPDO_PARA_START + tpdo_num - 1

    time_sync_tpdo = tpdo_node_od[tpdo_comm_index]["cob_id"].default == 0x181
    if time_sync_tpdo:
        rpdo_mapped_index = 0x2010
        rpdo_mapped_rec = rpdo_node_od[rpdo_mapped_index]
        rpdo_mapped_subindex = 0
    else:
        rpdo_mapped_index = 0x5000 + tpdo_node_od.node_id
        if rpdo_mapped_index not in rpdo_node_od:
            rpdo_mapped_rec = Record(tpdo_node_name, rpdo_mapped_index)
            rpdo_mapped_rec.description = f"{tpdo_node_name} tpdo mapped data"
            rpdo_node_od.add_object(rpdo_mapped_rec)

            # index 0 for node data index
            var = Variable("highest_index_supported", rpdo_mapped_index, 0x0)
            var.access_type = "const"
            var.data_type = canopen.objectdictionary.UNSIGNED8
            var.default = 0
            rpdo_mapped_rec.add_member(var)
        else:
            rpdo_mapped_rec = rpdo_node_od[rpdo_mapped_index]

    rpdo_node_od.device_information.nr_of_RXPDO += 1
    rpdo_num = rpdo_node_od.device_information.nr_of_RXPDO

    rpdo_comm_index = RPDO_COMM_START + rpdo_num - 1
    rpdo_comm_rec = Record(f"rpdo_{rpdo_num}_communication_parameters", rpdo_comm_index)
    rpdo_node_od.add_object(rpdo_comm_rec)

    var = Variable("cob_id", rpdo_comm_index, 0x1)
    var.access_type = "const"
    var.data_type = canopen.objectdictionary.UNSIGNED32
    var.default = tpdo_node_od[tpdo_comm_index][0x1].default  # get value from TPDO def
    rpdo_comm_rec.add_member(var)

    var = Variable("transmission_type", rpdo_comm_index, 0x2)
    var.access_type = "const"
    var.data_type = canopen.objectdictionary.UNSIGNED8
    var.default = 254
    rpdo_comm_rec.add_member(var)

    var = Variable("event_timer", rpdo_comm_index, 0x5)
    var.access_type = "const"
    var.data_type = canopen.objectdictionary.UNSIGNED16
    var.default = 0
    rpdo_comm_rec.add_member(var)

    # index 0 for comms index
    var = Variable("highest_index_supported", rpdo_comm_index, 0x0)
    var.access_type = "const"
    var.data_type = canopen.objectdictionary.UNSIGNED8
    var.default = sorted(list(rpdo_comm_rec.subindices))[-1]  # no subindex 3 or 4
    rpdo_comm_rec.add_member(var)

    rpdo_mapping_index = RPDO_PARA_START + rpdo_num - 1
    rpdo_mapping_rec = Record(f"rpdo_{rpdo_num}_mapping_parameters", rpdo_mapping_index)
    rpdo_node_od.add_object(rpdo_mapping_rec)

    # index 0 for map index
    var = Variable("highest_index_supported", rpdo_mapping_index, 0x0)
    var.access_type = "const"
    var.data_type = canopen.objectdictionary.UNSIGNED8
    var.default = 0
    rpdo_mapping_rec.add_member(var)

    for j in range(len(tpdo_node_od[tpdo_mapping_index])):
        if j == 0:
            continue  # skip

        tpdo_mapping_obj = tpdo_node_od[tpdo_mapping_index][j]

        # master node data
        if not time_sync_tpdo:
            rpdo_mapped_subindex = rpdo_mapped_rec[0].default + 1
            tpdo_mapped_index = (tpdo_mapping_obj.default >> 16) & 0xFFFF
            tpdo_mapped_subindex = (tpdo_mapping_obj.default >> 8) & 0xFF
            if isinstance(tpdo_node_od[tpdo_mapped_index], Variable):
                tpdo_mapped_obj = tpdo_node_od[tpdo_mapped_index]
                name = tpdo_mapped_obj.name
            else:
                tpdo_mapped_obj = tpdo_node_od[tpdo_mapped_index][tpdo_mapped_subindex]
                name = tpdo_node_od[tpdo_mapped_index].name + "_" + tpdo_mapped_obj.name
            var = Variable(name, rpdo_mapped_index, rpdo_mapped_subindex)
            var.description = tpdo_mapped_obj.description
            var.access_type = "rw"
            var.data_type = tpdo_mapped_obj.data_type
            var.default = tpdo_mapped_obj.default
            var.unit = tpdo_mapped_obj.unit
            var.factor = tpdo_mapped_obj.factor
            var.bit_definitions = deepcopy(tpdo_mapped_obj.bit_definitions)
            var.value_descriptions = deepcopy(tpdo_mapped_obj.value_descriptions)
            var.max = tpdo_mapped_obj.max
            var.min = tpdo_mapped_obj.min
            var.pdo_mappable = True
            rpdo_mapped_rec.add_member(var)

        # master node mapping obj
        rpdo_mapping_subindex = rpdo_mapping_rec[0].default + 1
        var = Variable(
            f"mapping_object_{rpdo_mapping_subindex}",
            rpdo_mapping_index,
            rpdo_mapping_subindex,
        )
        var.access_type = "const"
        var.data_type = canopen.objectdictionary.UNSIGNED32
        value = rpdo_mapped_index << 16
        value += rpdo_mapped_subindex << 8
        if rpdo_mapped_subindex == 0:
            rpdo_mapped_obj = rpdo_node_od[rpdo_mapped_index]
        else:
            rpdo_mapped_obj = rpdo_node_od[rpdo_mapped_index][rpdo_mapped_subindex]
        value += OD_DATA_TYPES[rpdo_mapped_obj.data_type].size
        var.default = value
        rpdo_mapping_rec.add_member(var)

        # update these
        if not time_sync_tpdo:
            rpdo_mapped_rec[0].default += 1
        rpdo_mapping_rec[0].default += 1


def _add_node_rpdo_data(
    config: CardConfig, od: ObjectDictionary, od_db: dict[str, ObjectDictionary]
) -> None:
    """Add all configured RPDO object to OD based off of TPDO objects from another OD."""

    for rpdo in config.rpdos:
        _add_rpdo_data(rpdo.tpdo_num, od, od_db[rpdo.card], rpdo.card)


def _add_all_rpdo_data(
    master_node_od: ObjectDictionary,
    node_od: ObjectDictionary,
    node_name: str,
) -> None:
    """Add all RPDO object to OD based off of TPDO objects from another OD."""

    if not node_od.device_information.nr_of_TXPDO:
        return  # no TPDOs

    for i in range(1, 17):
        if TPDO_COMM_START + i - 1 not in node_od:
            continue

        _add_rpdo_data(i, master_node_od, node_od, node_name)


def _load_std_objs(
    file_path: abc.Traversable, node_ids: dict[str, int]
) -> dict[str, Union[Variable, Record, Array]]:
    """Load the standard objects."""

    with resources.as_file(file_path) as path, path.open() as f:
        std_objs_raw = load(f, Loader=CLoader)

    std_objs = {}
    for obj_raw in std_objs_raw:
        obj = from_dict(data_class=IndexObject, data=obj_raw)
        if obj.object_type == "variable":
            std_objs[obj.name] = _make_var(obj, obj.index)
        elif obj.object_type == "record":
            std_objs[obj.name] = _make_rec(obj)
        elif obj.object_type == "array":
            std_objs[obj.name] = _make_arr(obj, node_ids)
    return std_objs


def overlay_configs(card_config: CardConfig, overlay_config: CardConfig) -> None:
    """deal with overlays"""

    # overlay object
    for obj in overlay_config.objects:
        overlayed = False
        for obj2 in card_config.objects:
            if obj.index != obj2.index:
                continue

            obj2.name = obj.name
            if obj.object_type == "variable":
                obj2.data_type = obj.data_type
                obj2.access_type = obj.access_type
                obj2.high_limit = obj.high_limit
                obj2.low_limit = obj.low_limit
            else:
                for sub_obj in obj.subindexes:
                    sub_overlayed = False
                    for sub_obj2 in obj2.subindexes:
                        if sub_obj.subindex == sub_obj2.subindex:
                            sub_obj2.name = sub_obj.name
                            sub_obj2.data_type = sub_obj.data_type
                            sub_obj2.access_type = sub_obj.access_type
                            sub_obj2.high_limit = sub_obj.high_limit
                            sub_obj2.low_limit = sub_obj.low_limit
                            overlayed = True
                            sub_overlayed = True
                            break  # obj was found, search for next one
                    if not sub_overlayed:  # add it
                        obj2.subindexes.append(deepcopy(sub_obj))
            overlayed = True
            break  # obj was found, search for next one
        if not overlayed:  # add it
            card_config.objects.append(deepcopy(obj))

    # overlay tpdos
    for overlay_tpdo in overlay_config.tpdos:
        overlayed = False
        for card_tpdo in card_config.tpdos:
            if card_tpdo.num == card_tpdo.num:
                card_tpdo.fields = overlay_tpdo.fields
                card_tpdo.event_timer_ms = overlay_tpdo.event_timer_ms
                card_tpdo.inhibit_time_ms = overlay_tpdo.inhibit_time_ms
                card_tpdo.sync = overlay_tpdo.sync
                overlayed = True
                break
        if not overlayed:  # add it
            card_config.tpdos.append(deepcopy(overlay_tpdo))

    # overlay rpdos
    for overlay_rpdo in overlay_config.rpdos:
        overlayed = False
        for card_rpdo in card_config.rpdos:
            if card_rpdo.num == card_rpdo.num:
                card_rpdo.card = overlay_rpdo.card
                card_rpdo.tpdo_num = overlay_rpdo.tpdo_num
                overlayed = True
                break
        if not overlayed:  # add it
            card_config.rpdos.append(deepcopy(overlay_rpdo))


def _load_configs(
    config_paths: dict[str, Card], overlays: dict[str, abc.Traversable]
) -> dict[str, CardConfig]:
    """Generate all ODs for a OreSat mission."""

    configs: dict[str, CardConfig] = {}

    for name, card in config_paths.items():
        if card.config is None:
            continue

        with resources.as_file(card.config) as path:
            card_config = CardConfig.from_yaml(path)

        with resources.as_file(card.common) as path:
            common_config = CardConfig.from_yaml(path)

        conf = CardConfig()
        conf.std_objects = list(set(common_config.std_objects + card_config.std_objects))
        conf.objects = common_config.objects + card_config.objects
        conf.rpdos = common_config.rpdos + card_config.rpdos
        if name == "c3":
            conf.fram = card_config.fram
            conf.tpdos = card_config.tpdos
        else:
            conf.tpdos = common_config.tpdos + card_config.tpdos

        if card.base in overlays:
            with resources.as_file(overlays[card.base]) as path:
                overlay_config = CardConfig.from_yaml(path)
            # because conf is cached by CardConfig, if multiple missions are loaded, the cached
            # version should not be modified because the changes will persist to later loaded
            # missions.
            conf = deepcopy(conf)
            overlay_configs(conf, overlay_config)

        configs[name] = conf

    return configs


def _gen_od_db(
    mission: Mission,
    cards: dict[str, Card],
    beacon_def: BeaconConfig,
    configs: dict[str, CardConfig],
) -> dict[str, ObjectDictionary]:
    od_db = {}
    node_ids = {name: cards[name].node_id for name in configs}
    node_ids["c3"] = 0x1

    std_objs = _load_std_objs(STD_OBJS_FILE_NAME, node_ids)

    # make od with common and card objects and tpdos
    for name, config in configs.items():
        od = ObjectDictionary()
        od.bitrate = 1_000_000  # bps
        od.node_id = cards[name].node_id
        od.device_information.allowed_baudrates = set([1000])
        od.device_information.vendor_name = "PSAS"
        od.device_information.vendor_number = 0
        od.device_information.product_name = cards[name].nice_name
        od.device_information.product_number = 0
        od.device_information.revision_number = 0
        od.device_information.order_code = 0
        od.device_information.simple_boot_up_master = False
        od.device_information.simple_boot_up_slave = False
        od.device_information.granularity = 8
        od.device_information.dynamic_channels_supported = False
        od.device_information.group_messaging = False
        od.device_information.nr_of_RXPDO = 0
        od.device_information.nr_of_TXPDO = 0
        od.device_information.LSS_supported = False

        # add common and card records
        _add_objects(od, config.objects, node_ids)

        # add any standard objects
        for obj_name in config.std_objects:
            od[std_objs[obj_name].index] = deepcopy(std_objs[obj_name])
            if obj_name == "cob_id_emergency_message":
                od["cob_id_emergency_message"].default = 0x80 + cards[name].node_id

        # add TPDSs
        _add_tpdo_data(od, config)

        # set specific obj defaults
        od["versions"]["configs_version"].default = __version__
        od["satellite_id"].default = mission.id
        for sat in Mission:
            od["satellite_id"].value_descriptions[sat.id] = sat.name.lower()
        if name == "c3":
            od["beacon"]["revision"].default = beacon_def.revision
            od["beacon"]["dest_callsign"].default = beacon_def.ax25.dest_callsign
            od["beacon"]["dest_ssid"].default = beacon_def.ax25.dest_ssid
            od["beacon"]["src_callsign"].default = beacon_def.ax25.src_callsign
            od["beacon"]["src_ssid"].default = beacon_def.ax25.src_ssid
            od["beacon"]["control"].default = beacon_def.ax25.control
            od["beacon"]["command"].default = beacon_def.ax25.command
            od["beacon"]["response"].default = beacon_def.ax25.response
            od["beacon"]["pid"].default = beacon_def.ax25.pid
            od["flight_mode"].access_type = "ro"

        od_db[name] = od

    # add all RPDOs
    for name in configs:
        if name == "c3":
            continue
        _add_all_rpdo_data(od_db["c3"], od_db[name], name)
        _add_node_rpdo_data(configs[name], od_db[name], od_db)

    # set all object values to its default value
    for od in od_db.values():
        for index in od:
            if not isinstance(od[index], Variable):
                for subindex in od[index]:
                    od[index][subindex].value = od[index][subindex].default
            else:
                od[index].value = od[index].default

    return od_db


def _gen_c3_fram_defs(c3_od: ObjectDictionary, config: CardConfig) -> list[Variable]:
    """Get the list of objects in saved to fram."""

    fram_objs = []

    for fields in config.fram:
        obj = None
        if len(fields) == 1:
            obj = c3_od[fields[0]]
        elif len(fields) == 2:
            obj = c3_od[fields[0]][fields[1]]
        if obj is not None:
            fram_objs.append(obj)

    return fram_objs


def _gen_c3_beacon_defs(c3_od: ObjectDictionary, beacon_def: BeaconConfig) -> list[Variable]:
    """Get the list of objects in the beacon from OD."""

    beacon_objs = []

    for fields in beacon_def.fields:
        obj = None
        if len(fields) == 1:
            obj = c3_od[fields[0]]
        elif len(fields) == 2:
            obj = c3_od[fields[0]][fields[1]]
        if obj is not None:
            beacon_objs.append(obj)

    return beacon_objs


def _gen_fw_base_od(mission: Mission) -> ObjectDictionary:
    """Generate all ODs for a OreSat mission."""

    od = ObjectDictionary()
    od.bitrate = 1_000_000  # bps
    od.node_id = 0x7C
    od.device_information.allowed_baudrates = set([1000])  # kpbs
    od.device_information.vendor_name = "PSAS"
    od.device_information.vendor_number = 0
    od.device_information.product_name = "Firmware Base"
    od.device_information.product_number = 0
    od.device_information.revision_number = 0
    od.device_information.order_code = 0
    od.device_information.simple_boot_up_master = False
    od.device_information.simple_boot_up_slave = False
    od.device_information.granularity = 8
    od.device_information.dynamic_channels_supported = False
    od.device_information.group_messaging = False
    od.device_information.nr_of_RXPDO = 0
    od.device_information.nr_of_TXPDO = 0
    od.device_information.LSS_supported = False

    with resources.as_file(resources.files(base) / "fw_common.yaml") as path:
        config = CardConfig.from_yaml(path)

    _add_objects(od, config.objects, {})

    std_objs = _load_std_objs(STD_OBJS_FILE_NAME, {})
    for name in config.std_objects:
        od[std_objs[name].index] = deepcopy(std_objs[name])
        if name == "cob_id_emergency_message":
            od["cob_id_emergency_message"].default = 0x80 + od.node_id

    # add TPDSs
    _add_tpdo_data(od, config)

    # set specific obj defaults
    od["versions"]["configs_version"].default = __version__
    od["satellite_id"].default = mission.id

    return od
