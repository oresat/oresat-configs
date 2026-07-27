"""Convert OreSat configs to ODs."""

import dataclasses
from copy import deepcopy
from typing import Literal

from canopen.objectdictionary import ObjectDictionary, ODArray, ODRecord, ODVariable
from yaml import CLoader, load

from .beacon_config import BeaconConfig
from .card_config import CardConfig, IndexObject, Rpdo, SubindexObject
from .card_info import Card
from .constants import Mission, __version__


def _load_configs(
    mission: Mission,
    cards: dict[str, Card],
) -> dict[str, CardConfig]:
    """Generate all ODs for a OreSat mission."""
    node_ids = {name: card.node_id for name, card in cards.items()}

    standard_objects = {}
    with mission.standard.open() as f:
        for raw in load(f, Loader=CLoader):
            obj = IndexObject.from_dict(raw, node_ids)
            standard_objects[obj.name] = obj

    common_configs: dict[str | None, CardConfig] = {None: CardConfig()}
    for style, file in mission.common.items():
        common_configs[style] = CardConfig.from_yaml(file, node_ids)


    configs: dict[str, CardConfig] = {}
    for name, card in cards.items():
        if card.basetype is None:  # some cards are OPD only
            continue

        conf = CardConfig.from_yaml(mission.configs[card.basename], node_ids)

        common = common_configs[card.basetype]
        conf.std_objects = list(set(common.std_objects + conf.std_objects))
        conf.update(common)
        if name != "c3":
            conf.tpdos.extend(common.tpdos)
            conf.rpdos.extend(common.rpdos)

        if card.basename in mission.overlays:
            conf.overlay(CardConfig.from_yaml(mission.overlays[card.basename], node_ids))

        for std in conf.std_objects:
            obj = standard_objects[std]
            if std == "cob_id_emergency_message":
                obj = dataclasses.replace(obj, default=0x80 + card.node_id)
            conf[obj.name] = obj

        configs[name] = conf

    # The C3, serving as the consumer of all TPDOs, needs corresponding RPDOs created.
    c3 = configs['c3']
    for name, conf in configs.items():
        if name == 'c3':
            continue

        subindexes: list[SubindexObject] = []
        # sorted ostensibly doesn't matter but it keeps the OD generation the same as past versions
        for tpdo in sorted(conf.tpdos, key=lambda x: x.num):
            rpdo = Rpdo(len(c3.rpdos) + 1, name, tpdo.num)
            for field in tpdo.fields:
                rpdo.fields.append([name, '_'.join(field)])
                if len(field) == 1:
                    entry = conf[field[0]]
                else:
                    entry = conf[field[0]][field[1]]
                subindexes.append(
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
                        subindex=len(subindexes) + 1,
                    )
                )
            c3.rpdos.append(rpdo)

        c3[name] = IndexObject(
            name=name,
            description=f'{name} tpdo mapped data',
            index=0x5000 + node_ids[name],
            object_type='record',
            subindexes=subindexes
        )

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
        od = ObjectDictionary()
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
        for obj in config.values():
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
        assert isinstance(versions, ODRecord)
        # FIXME: canopen is still working out their type annotations, default should be of type
        #        Union[int, str, bytes, None] but is Optional[int]. Remove ignore when upstream
        #        fixes it.
        versions["configs_version"].default = __version__  # type: ignore[assignment]
        satellite_id = od["satellite_id"]
        assert isinstance(satellite_id, ODVariable)
        satellite_id.default = mission.id
        for sat in Mission:
            satellite_id.value_descriptions[sat.id] = sat.name.lower()
        if name == "c3":
            beacon = od["beacon"]
            assert isinstance(beacon, ODRecord)
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
            assert isinstance(flight_mode, ODVariable)
            flight_mode.access_type = "ro"

        od_db[name] = od

    # set all object values to its default value
    for od in od_db.values():
        for entry in od.values():
            if not isinstance(entry, ODVariable):
                for subentry in entry.values():
                    subentry.value = subentry.default
            else:
                entry.value = entry.default

    return od_db


def _gen_c3_fram_defs(c3_od: ObjectDictionary, config: CardConfig) -> list[ODVariable]:
    """Get the list of objects in saved to fram."""
    fram_objs = []

    for fields in config.fram:
        obj = None
        if len(fields) >= 1:
            obj = c3_od[fields[0]]
        if len(fields) == 2:
            assert isinstance(obj, (ODRecord, ODArray))
            obj = obj[fields[1]]
        if obj is not None:
            assert isinstance(obj, ODVariable)
            fram_objs.append(obj)

    return fram_objs


def _gen_c3_beacon_defs(c3_od: ObjectDictionary, beacon_def: BeaconConfig) -> list[ODVariable]:
    """Get the list of objects in the beacon from OD."""
    beacon_objs = []

    for fields in beacon_def.fields:
        obj = None
        if len(fields) >= 1:
            obj = c3_od[fields[0]]
        if len(fields) == 2:
            assert isinstance(obj, (ODRecord, ODArray))
            obj = obj[fields[1]]
        if obj is not None:
            assert isinstance(obj, ODVariable)
            beacon_objs.append(obj)

    return beacon_objs


def _gen_fw_base_od(mission: Mission) -> ObjectDictionary:
    """Generate all ODs for a OreSat mission."""
    od = ObjectDictionary()
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

    config = CardConfig.from_yaml(mission.common['fw'], {})

    # add card objects
    for obj in config.values():
        if obj.index in od.indices:
            raise ValueError(f"index 0x{obj.index:X} already in OD")
        od.add_object(obj.to_entry())

    # add any standard objects
    with mission.standard.open() as f:
        for raw in load(f, Loader=CLoader):
            if raw['name'] in config.std_objects:
                obj = IndexObject.from_dict(raw, {})
                if obj.name == "cob_id_emergency_message":
                    obj = dataclasses.replace(obj, default=0x80 + od.node_id)
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
    assert isinstance(versions, ODRecord)
    # FIXME: canopen is still working out their type annotations, default should be of type
    #        Union[int, str, bytes, None] but is Optional[int]. Remove ignore when upstream
    #        fixes it.
    versions["configs_version"].default = __version__  # type: ignore[assignment]
    satellite_id = od["satellite_id"]
    assert isinstance(satellite_id, ODVariable)
    satellite_id.default = mission.id

    return od
