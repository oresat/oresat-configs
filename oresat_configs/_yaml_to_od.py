"""Convert OreSat configs to ODs."""

from __future__ import annotations

import dataclasses
from copy import deepcopy
from importlib import abc, resources
from typing import TYPE_CHECKING

import canopen
from canopen import ObjectDictionary
from canopen.objectdictionary import Array, Record, Variable
from yaml import CLoader, load

from . import base
from .card_config import CardConfig, IndexObject, Rpdo, SubindexObject
from .constants import Mission, __version__

if TYPE_CHECKING:
    from .beacon_config import BeaconConfig
    from .card_info import Card


STD_OBJS_FILE_NAME = resources.files("oresat_configs") / "standard_objects.yaml"


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
    cards: dict[str, Card],
    overlays: dict[str, abc.Traversable],
) -> dict[str, CardConfig]:
    """Generate all ODs for a OreSat mission."""

    standard_objects = {}
    with resources.as_file(STD_OBJS_FILE_NAME) as path, path.open() as f:
        for raw in load(f, Loader=CLoader):
            obj = IndexObject.from_dict(raw)
            standard_objects[obj.name] = obj

    common_configs: dict[abc.Traversable | None, CardConfig] = {None: CardConfig()}
    for file in {card.common for card in cards.values() if card.common is not None}:
        with resources.as_file(file) as path:
            common_configs[file] = CardConfig.from_yaml(path)

    node_ids = {name: card.node_id for name, card in cards.items()}

    configs: dict[str, CardConfig] = {}
    for name, card in cards.items():
        if card.config is None:  # some cards are OPD only
            continue

        with resources.as_file(card.config) as path:
            conf = CardConfig.from_yaml(path)

        common = common_configs[card.common]
        conf.std_objects = list(set(common.std_objects + conf.std_objects))
        conf.objects.extend(common.objects)
        if name != "c3":
            conf.tpdos.extend(common.tpdos)
            conf.rpdos.extend(common.rpdos)

        if card.base in overlays:
            with resources.as_file(overlays[card.base]) as path:
                overlay_config = CardConfig.from_yaml(path)
            overlay_configs(conf, overlay_config)

        for std in conf.std_objects:
            obj = standard_objects[std]
            if std == "cob_id_emergency_message":
                obj = dataclasses.replace(obj, default=0x80 + card.node_id)
            conf.objects.append(obj)

        for obj in conf.objects:
            obj.expand_subindexes(node_ids)

        configs[name] = conf

    # The C3, serving as the consumer of all TPDOs, needs corresponding RPDOs created.
    c3 = configs['c3']
    for name, conf in configs.items():
        if name == 'c3':
            continue

        mapped_card = IndexObject(
            name=name,
            description=f'{name} tpdo mapped data',
            index=0x5000 + node_ids[name],
            object_type='record',
        )
        # sorted ostensibly doesn't matter but it keeps the OD generation the same as past versions
        for tpdo in sorted(conf.tpdos, key=lambda x: x.num):
            rpdo = Rpdo(len(c3.rpdos) + 1, name, tpdo.num)
            for field in tpdo.fields:
                rpdo.fields.append([name, '_'.join(field)])
                entry = conf.find_object(field)
                mapped_card.subindexes.append(
                    SubindexObject(
                        name='_'.join(field),
                        data_type=entry.data_type,
                        length=1,
                        access_type='rw',
                        default=entry.default,
                        description=entry.description,
                        value_descriptions=deepcopy(entry.value_descriptions),
                        bit_definitions=deepcopy(entry.bit_definitions),
                        unit=entry.unit,
                        scale_factor=entry.scale_factor,
                        low_limit=entry.low_limit,
                        high_limit=entry.high_limit,
                        subindex=len(mapped_card.subindexes) + 1,
                    )
                )
            c3.rpdos.append(rpdo)
        c3.objects.append(mapped_card)

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
            od.add_object(obj.to_entry())

        # add PPDSs
        # FIXME: canopen is still working on improving their type annotations. nr_of_TXPDOs is
        #        marked as a bool which is clearly wrong. Remove the ignore when upstream fixes
        #        their types
        od.device_information.nr_of_TXPDO += len(config.tpdos)  # type: ignore[operator,assignment]
        for tpdo in config.tpdos:
            od.add_object(tpdo.to_mapping_parameter(od))
            od.add_object(tpdo.to_communication_parameter(od.node_id))

        od.device_information.nr_of_RXPDO += len(config.rpdos)  # type: ignore[operator,assignment]
        for rpdo in config.rpdos:
            od.add_object(rpdo.to_mapping_parameter(od))
            od.add_object(rpdo.to_communication_parameter(node_ids[rpdo.card]))

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
        obj.expand_subindexes({})
        od.add_object(obj.to_entry())

    # add any standard objects
    with resources.as_file(STD_OBJS_FILE_NAME) as path, path.open() as f:
        for raw in load(f, Loader=CLoader):
            if raw['name'] in config.std_objects:
                obj = IndexObject.from_dict(raw)
                if obj.name == "cob_id_emergency_message":
                    obj = dataclasses.replace(obj, default=0x80 + od.node_id)
                obj.expand_subindexes({})
                od.add_object(obj.to_entry())

    # add TPDSs
    # FIXME: canopen is still working on improving their type annotations. nr_of_TXPDOs is
    #        marked as a bool which is clearly wrong. Remove the ignore when upstream fixes
    #        their types
    od.device_information.nr_of_TXPDO += len(config.tpdos)  # type: ignore[operator,assignment]
    for tpdo in config.tpdos:
        od.add_object(tpdo.to_mapping_parameter(od))
        od.add_object(tpdo.to_communication_parameter(od.node_id))

    od.device_information.nr_of_RXPDO += len(config.rpdos)  # type: ignore[operator,assignment]
    for rpdo in config.rpdos:
        od.add_object(rpdo.to_mapping_parameter(od))
        od.add_object(rpdo.to_communication_parameter(0x1))  # c3

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
