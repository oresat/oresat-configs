"""Convert OreSat configs to ODs."""

from __future__ import annotations

from copy import deepcopy
from importlib import abc, resources
from typing import TYPE_CHECKING, cast

import canopen
from canopen import ObjectDictionary
from canopen.objectdictionary import Array, Record, Variable
from yaml import CLoader, load

from . import base
from .card_config import CardConfig, IndexObject
from .constants import Mission, __version__

if TYPE_CHECKING:
    from .beacon_config import BeaconConfig
    from .card_info import Card


STD_OBJS_FILE_NAME = resources.files("oresat_configs") / "standard_objects.yaml"

RPDO_COMM_START = 0x1400
RPDO_PARA_START = 0x1600
TPDO_COMM_START = 0x1800
TPDO_PARA_START = 0x1A00


OD_DATA_SIZE = {
    canopen.objectdictionary.BOOLEAN: 8,
    canopen.objectdictionary.INTEGER8: 8,
    canopen.objectdictionary.INTEGER16: 16,
    canopen.objectdictionary.INTEGER32: 32,
    canopen.objectdictionary.INTEGER64: 64,
    canopen.objectdictionary.UNSIGNED8: 8,
    canopen.objectdictionary.UNSIGNED16: 16,
    canopen.objectdictionary.UNSIGNED32: 32,
    canopen.objectdictionary.UNSIGNED64: 64,
    canopen.objectdictionary.REAL32: 32,
    canopen.objectdictionary.REAL64: 64,
    canopen.objectdictionary.VISIBLE_STRING: 0,
    canopen.objectdictionary.OCTET_STRING: 0,
    canopen.objectdictionary.DOMAIN: 0,
}


def _add_tpdo_data(od: ObjectDictionary, config: CardConfig) -> None:
    """Add tpdo objects to OD."""

    for tpdo in config.tpdos:
        # FIXME: canopen is still working on improving their type annotations. nr_of_TXPDOs is
        #        marked as a bool which is clearly wrong. Remove the ignore when upstream fixes
        #        their types
        od.device_information.nr_of_TXPDO += 1  # type: ignore[operator,assignment]

        map_index = TPDO_PARA_START + tpdo.num - 1
        map_rec = Record(f"tpdo_{tpdo.num}_mapping_parameters", map_index)
        od.add_object(map_rec)

        # index 0 for mapping index
        var0 = Variable("highest_index_supported", map_index, 0x0)
        var0.access_type = "const"
        var0.data_type = canopen.objectdictionary.UNSIGNED8
        map_rec.add_member(var0)

        for t_field in tpdo.fields:
            subindex = tpdo.fields.index(t_field) + 1
            var = Variable(
                f"mapping_object_{subindex}",
                map_index,
                subindex,
            )
            var.access_type = "const"
            var.data_type = canopen.objectdictionary.UNSIGNED32

            mapped_obj = od[t_field[0]]
            if isinstance(mapped_obj, (Record, Array)):
                mapped_obj = mapped_obj[t_field[1]]
            mapped_subindex = mapped_obj.subindex
            value = mapped_obj.index << 16
            value += mapped_subindex << 8
            assert mapped_obj.data_type is not None
            value += OD_DATA_SIZE[mapped_obj.data_type]
            var.default = value
            map_rec.add_member(var)

        var0.default = len(map_rec) - 1

        comm_index = TPDO_COMM_START + tpdo.num - 1
        comm_rec = Record(f"tpdo_{tpdo.num}_communication_parameters", comm_index)
        od.add_object(comm_rec)

        # index 0 for comms index
        var0 = Variable("highest_index_supported", comm_index, 0x0)
        var0.access_type = "const"
        var0.data_type = canopen.objectdictionary.UNSIGNED8
        var0.default = 0x6
        comm_rec.add_member(var0)

        var = canopen.objectdictionary.Variable("cob_id", comm_index, 0x1)
        var.access_type = "const"
        var.data_type = canopen.objectdictionary.UNSIGNED32
        node_id = od.node_id
        assert node_id is not None
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
    assert tpdo_node_od.node_id is not None
    tpdo_comm = tpdo_node_od[TPDO_COMM_START + tpdo_num - 1]
    assert isinstance(tpdo_comm, Record)
    tpdo_mapping = tpdo_node_od[TPDO_PARA_START + tpdo_num - 1]
    assert isinstance(tpdo_mapping, Record)

    time_sync_tpdo = tpdo_comm["cob_id"].default == 0x181
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
            var = canopen.objectdictionary.Variable(
                "highest_index_supported",
                rpdo_mapped_index,
                0x0,
            )
            var.access_type = "const"
            var.data_type = canopen.objectdictionary.UNSIGNED8
            var.default = 0
            rpdo_mapped_rec.add_member(var)
        else:
            rpdo_mapped_rec = rpdo_node_od[rpdo_mapped_index]

    # FIXME: canopen is still working on improving their type annotations. nr_of_RXPDO is marked as
    #        a bool which is clearly wrong. Remove the ignore and cast when upstream fixes things.
    rpdo_node_od.device_information.nr_of_RXPDO += 1  # type: ignore[operator,assignment]
    rpdo_num = cast(int, rpdo_node_od.device_information.nr_of_RXPDO)

    rpdo_comm_index = RPDO_COMM_START + rpdo_num - 1
    rpdo_comm_rec = canopen.objectdictionary.Record(
        f"rpdo_{rpdo_num}_communication_parameters",
        rpdo_comm_index,
    )
    rpdo_node_od.add_object(rpdo_comm_rec)

    var = Variable("cob_id", rpdo_comm_index, 0x1)
    var.access_type = "const"
    var.data_type = canopen.objectdictionary.UNSIGNED32
    var.default = tpdo_comm[0x1].default  # get value from TPDO def
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
    var.default = sorted(rpdo_comm_rec.subindices)[-1]  # no subindex 3 or 4
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
    assert rpdo_mapping_rec[0].default is not None

    for j in range(len(tpdo_mapping)):
        if j == 0:
            continue  # skip

        tpdo_mapping_obj = tpdo_mapping[j]
        assert tpdo_mapping_obj.default is not None

        # master node data
        if not time_sync_tpdo:
            assert isinstance(rpdo_mapped_rec, Record)
            assert rpdo_mapped_rec[0].default is not None

            rpdo_mapped_subindex = rpdo_mapped_rec[0].default + 1
            mapped_tpdo = tpdo_node_od[(tpdo_mapping_obj.default >> 16) & 0xFFFF]
            tpdo_mapped_subindex = (tpdo_mapping_obj.default >> 8) & 0xFF
            if isinstance(mapped_tpdo, Variable):
                name = mapped_tpdo.name
            else:
                name = mapped_tpdo.name + "_" + mapped_tpdo[tpdo_mapped_subindex].name
                mapped_tpdo = mapped_tpdo[tpdo_mapped_subindex]
            var = Variable(name, rpdo_mapped_index, rpdo_mapped_subindex)
            var.description = mapped_tpdo.description
            var.access_type = "rw"
            var.data_type = mapped_tpdo.data_type
            var.default = mapped_tpdo.default
            var.unit = mapped_tpdo.unit
            var.factor = mapped_tpdo.factor
            var.bit_definitions = deepcopy(mapped_tpdo.bit_definitions)
            var.value_descriptions = deepcopy(mapped_tpdo.value_descriptions)
            var.max = mapped_tpdo.max
            var.min = mapped_tpdo.min
            var.pdo_mappable = True
            rpdo_mapped_rec.add_member(var)

        # master node mapping obj
        rpdo_mapping_subindex = rpdo_mapping_rec[0].default + 1
        var = canopen.objectdictionary.Variable(
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
            obj = rpdo_node_od[rpdo_mapped_index]
            assert isinstance(obj, (Record, Array))
            rpdo_mapped_obj = obj[rpdo_mapped_subindex]
        assert isinstance(rpdo_mapped_obj, Variable)
        assert rpdo_mapped_obj.data_type is not None
        value += OD_DATA_SIZE[rpdo_mapped_obj.data_type]
        var.default = value
        rpdo_mapping_rec.add_member(var)

        # update these
        if not time_sync_tpdo:
            assert isinstance(rpdo_mapped_rec, Record)
            assert rpdo_mapped_rec[0].default is not None
            rpdo_mapped_rec[0].default += 1
        rpdo_mapping_rec[0].default += 1


def _add_node_rpdo_data(
    config: CardConfig,
    od: ObjectDictionary,
    od_db: dict[str, ObjectDictionary],
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
    config_paths: dict[str, Card],
    overlays: dict[str, abc.Traversable],
) -> dict[str, CardConfig]:
    """Generate all ODs for a OreSat mission."""

    configs: dict[str, CardConfig] = {}

    for name, card in config_paths.items():
        if card.config is None:
            continue
        assert card.common is not None

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

    with resources.as_file(STD_OBJS_FILE_NAME) as path, path.open() as f:
        std_objs_raw = load(f, Loader=CLoader)

    # make od with common and card objects and tpdos
    for name, config in configs.items():
        od = canopen.ObjectDictionary()
        od.bitrate = 1_000_000  # bps
        od.node_id = cards[name].node_id
        od.device_information.allowed_baudrates = {1000}
        od.device_information.vendor_name = "PSAS"
        od.device_information.vendor_number = 0
        od.device_information.product_name = cards[name].nice_name
        od.device_information.product_number = 0
        od.device_information.revision_number = 0
        od.device_information.order_code = None
        od.device_information.simple_boot_up_master = False
        od.device_information.simple_boot_up_slave = False
        od.device_information.granularity = 8
        od.device_information.dynamic_channels_supported = False
        od.device_information.group_messaging = False
        od.device_information.nr_of_RXPDO = 0  # type: ignore[assignment]
        od.device_information.nr_of_TXPDO = 0  # type: ignore[assignment]
        od.device_information.LSS_supported = False

        # add card objects
        for obj in config.objects:
            if obj.index in od.indices:
                raise ValueError(f"index 0x{obj.index:X} already in OD")
            od.add_object(obj.to_entry(node_ids))

        # add any standard objects
        for obj_raw in std_objs_raw:
            if obj_raw['name'] in config.std_objects:
                obj = IndexObject.from_dict(obj_raw)
                if obj.name == "cob_id_emergency_message":
                    obj.default = 0x80 + cards[name].node_id
                od.add_object(obj.to_entry(node_ids))

        # add TPDSs
        _add_tpdo_data(od, config)

        # set specific obj defaults
        versions = od["versions"]
        assert isinstance(versions, Record)
        # FIXME: canopen is still working out their type annotations, default should be of type
        #        Union[int, str, bytes, None] but is Optional[int]. Remove ignore when upstream
        #        fixes it.
        versions["configs_version"].default = __version__  # type: ignore[assignment]
        satellite_id = od["satellite_id"]
        assert isinstance(satellite_id, Variable)
        satellite_id.default = mission.id
        for sat in Mission:
            satellite_id.value_descriptions[sat.id] = sat.name.lower()
        if name == "c3":
            beacon = od["beacon"]
            assert isinstance(beacon, Record)
            beacon["revision"].default = beacon_def.revision
            beacon["dest_callsign"].default = beacon_def.ax25.dest_callsign  # type: ignore[assignment]
            beacon["dest_ssid"].default = beacon_def.ax25.dest_ssid
            beacon["src_callsign"].default = beacon_def.ax25.src_callsign  # type: ignore[assignment]
            beacon["src_ssid"].default = beacon_def.ax25.src_ssid
            beacon["control"].default = beacon_def.ax25.control
            beacon["command"].default = beacon_def.ax25.command
            beacon["response"].default = beacon_def.ax25.response
            beacon["pid"].default = beacon_def.ax25.pid
            flight_mode = od["flight_mode"]
            assert isinstance(flight_mode, Variable)
            flight_mode.access_type = "ro"

        od_db[name] = od

    # add all RPDOs
    for name, config in configs.items():
        if name == "c3":
            continue
        _add_all_rpdo_data(od_db["c3"], od_db[name], name)
        _add_node_rpdo_data(config, od_db[name], od_db)

    # set all object values to its default value
    for od in od_db.values():
        for entry in od.values():
            if not isinstance(entry, Variable):
                for subentry in entry.values():
                    subentry.value = subentry.default
            else:
                entry.value = entry.default

    return od_db


def _gen_c3_fram_defs(c3_od: ObjectDictionary, config: CardConfig) -> list[Variable]:
    """Get the list of objects in saved to fram."""

    fram_objs = []

    for fields in config.fram:
        obj = None
        if len(fields) >= 1:
            obj = c3_od[fields[0]]
        if len(fields) == 2:
            assert isinstance(obj, (Record, Array))
            obj = obj[fields[1]]
        if obj is not None:
            assert isinstance(obj, Variable)
            fram_objs.append(obj)

    return fram_objs


def _gen_c3_beacon_defs(c3_od: ObjectDictionary, beacon_def: BeaconConfig) -> list[Variable]:
    """Get the list of objects in the beacon from OD."""

    beacon_objs = []

    for fields in beacon_def.fields:
        obj = None
        if len(fields) >= 1:
            obj = c3_od[fields[0]]
        if len(fields) == 2:
            assert isinstance(obj, (Record, Array))
            obj = obj[fields[1]]
        if obj is not None:
            assert isinstance(obj, Variable)
            beacon_objs.append(obj)

    return beacon_objs


def _gen_fw_base_od(mission: Mission) -> canopen.ObjectDictionary:
    """Generate all ODs for a OreSat mission."""

    od = canopen.ObjectDictionary()
    od.bitrate = 1_000_000  # bps
    od.node_id = 0x7C
    od.device_information.allowed_baudrates = {1000}  # kpbs
    od.device_information.vendor_name = "PSAS"
    od.device_information.vendor_number = 0
    od.device_information.product_name = "Firmware Base"
    od.device_information.product_number = 0
    od.device_information.revision_number = 0
    od.device_information.order_code = None
    od.device_information.simple_boot_up_master = False
    od.device_information.simple_boot_up_slave = False
    od.device_information.granularity = 8
    od.device_information.dynamic_channels_supported = False
    od.device_information.group_messaging = False
    od.device_information.nr_of_RXPDO = 0  # type: ignore[assignment]
    od.device_information.nr_of_TXPDO = 0  # type: ignore[assignment]
    od.device_information.LSS_supported = False

    with resources.as_file(resources.files(base) / "fw_common.yaml") as path:
        config = CardConfig.from_yaml(path)

    # add card objects
    for obj in config.objects:
        if obj.index in od.indices:
            raise ValueError(f"index 0x{obj.index:X} already in OD")
        od.add_object(obj.to_entry({}))

    # add any standard objects
    with resources.as_file(STD_OBJS_FILE_NAME) as path, path.open() as f:
        for raw in load(f, Loader=CLoader):
            if raw['name'] in config.std_objects:
                obj = IndexObject.from_dict(raw)
                if obj.name == "cob_id_emergency_message":
                    obj.default = 0x80 + od.node_id
                od.add_object(obj.to_entry({}))

    # add TPDSs
    _add_tpdo_data(od, config)

    # set specific obj defaults
    versions = od["versions"]
    assert isinstance(versions, Record)
    # FIXME: canopen is still working out their type annotations, default should be of type
    #        Union[int, str, bytes, None] but is Optional[int]. Remove ignore when upstream
    #        fixes it.
    versions["configs_version"].default = __version__  # type: ignore[assignment]
    satellite_id = od["satellite_id"]
    assert isinstance(satellite_id, Variable)
    satellite_id.default = mission.id

    return od
