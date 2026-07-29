"""Convert OreSat configs to ODs."""

import dataclasses
from copy import deepcopy
from importlib.abc import Traversable

from canopen.objectdictionary import ObjectDictionary, ODArray, ODRecord, ODVariable
from yaml import CLoader, load

from .beacon_config import BeaconConfig
from .card_config import CardConfig, ConfigObject, IndexObject, Rpdo, SubindexObject
from .card_info import Card
from .constants import Mission, __version__


def _standard_objects(mission: Mission, node_ids: dict[str, int]) -> dict[str, IndexObject]:
    standard_objects: dict[str, IndexObject] = {}
    with mission.standard.open() as f:
        for raw in load(f, Loader=CLoader):
            obj = IndexObject.from_dict(raw, node_ids)
            standard_objects[obj.name] = obj
    return standard_objects


def _common_config(file: Traversable, mission: Mission, node_ids: dict[str, int]) -> CardConfig:
    common = CardConfig.from_yaml(file, node_ids)
    # set specific obj defaults
    common["versions"]["configs_version"].default = __version__
    common["satellite_id"].default = mission.id
    for sat in Mission:
        common["satellite_id"].value_descriptions[sat.name.lower()] = sat.id
    return common


def _add_standard_objects(
    conf: CardConfig, card: Card, standard_objects: dict[str, IndexObject]
) -> None:
    for std in conf.std_objects:
        obj = standard_objects[std]
        if std == "cob_id_emergency_message":
            obj = dataclasses.replace(obj, default=0x80 + card.node_id)
        conf[obj.name] = obj


def _load_configs(
    mission: Mission,
    beacon_def: BeaconConfig,
    cards: dict[str, Card],
) -> dict[str, CardConfig]:
    """Generate all ODs for a OreSat mission."""
    node_ids = {name: card.node_id for name, card in cards.items()}

    standard_objects = _standard_objects(mission, node_ids)
    common_configs: dict[str, CardConfig] = {}
    for style, file in mission.common.items():
        common_configs[style] = _common_config(file, mission, node_ids)

    configs: dict[str, CardConfig] = {}
    for name, card in cards.items():
        if card.basetype is None:  # some cards are OPD only
            continue

        conf = deepcopy(common_configs[card.basetype])
        conf.overlay(CardConfig.from_yaml(mission.configs[card.basename], node_ids))
        if card.basename in mission.overlays:
            conf.overlay(CardConfig.from_yaml(mission.overlays[card.basename], node_ids))

        _add_standard_objects(conf, card, standard_objects)

        configs[name] = conf

    # The C3, serving as the consumer of all TPDOs, needs corresponding RPDOs created.
    c3 = configs['c3']
    c3.rpdos = []
    # FIXME: This is a hack to set the scet tpdo as acyclic. To do this properly we should probably
    # rethink how overlays and the yaml data model interact better.
    c3.tpdos[0].event_timer_ms = 0
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
                    entry: ConfigObject = conf[field[0]]
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
            subindexes=subindexes,
        )

    beacon = c3["beacon"]
    beacon["revision"].default = beacon_def.revision
    beacon["dest_callsign"].default = beacon_def.ax25.dest_callsign
    beacon["dest_ssid"].default = beacon_def.ax25.dest_ssid
    beacon["src_callsign"].default = beacon_def.ax25.src_callsign
    beacon["src_ssid"].default = beacon_def.ax25.src_ssid
    beacon["control"].default = beacon_def.ax25.control
    beacon["command"].default = beacon_def.ax25.command
    beacon["response"].default = beacon_def.ax25.response
    beacon["pid"].default = beacon_def.ax25.pid
    c3["flight_mode"].access_type = "ro"

    return configs


def make_od(name: str, cards: dict[str, Card], config: CardConfig) -> ObjectDictionary:
    od = ObjectDictionary()
    od.bitrate = 1_000_000  # bps
    od.node_id = cards[name].node_id
    info = od.device_information
    info.allowed_baudrates = {1000}
    info.vendor_name = "PSAS"
    info.vendor_number = 0
    info.product_name = cards[name].nice_name
    info.product_number = 0
    info.revision_number = 0
    info.order_code = None
    info.simple_boot_up_master = False
    info.simple_boot_up_slave = False
    info.granularity = 8
    info.dynamic_channels_supported = False
    info.group_messaging = False
    info.nr_of_RXPDO = 0  # type: ignore[assignment]
    info.nr_of_TXPDO = 0  # type: ignore[assignment]
    info.LSS_supported = False

    # add card objects
    for obj in config.values():
        if obj.index in od.indices:
            raise ValueError(f"index 0x{obj.index:X} already in OD")
        od.add_object(obj.to_entry())

    # add PDOs
    # FIXME: canopen is still working on improving their type annotations. nr_of_TXPDOs is
    #        marked as a bool which is clearly wrong. Remove the ignore when upstream fixes
    #        their types
    info.nr_of_TXPDO += len(config.tpdos)  # type: ignore[operator,assignment]
    for tpdo in config.tpdos:
        od.add_object(tpdo.to_mapping_parameter(od))
        od.add_object(tpdo.to_communication_parameter(od.node_id))

    info.nr_of_RXPDO += len(config.rpdos)  # type: ignore[operator,assignment]
    for rpdo in config.rpdos:
        od.add_object(rpdo.to_mapping_parameter(od))
        od.add_object(rpdo.to_communication_parameter(cards[rpdo.card].node_id))

    # set all object values to its default value
    for entry in od.values():
        if isinstance(entry, ODVariable):
            entry.value = entry.default
        else:
            for subentry in entry.values():
                subentry.value = subentry.default

    return od


def _gen_od_db(
    cards: dict[str, Card], configs: dict[str, CardConfig]
) -> dict[str, ObjectDictionary]:
    # make od with common and card objects and tpdos
    return {name: make_od(name, cards, config) for name, config in configs.items()}


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
    """Generate an OD for just a generic firmware card."""
    node_ids = {"c3": 0x01, "fw_base": 0x7C}
    card = Card(
        name='fw_base',
        nice_name="Firmware Base",
        node_id=node_ids["fw_base"],
        processor="mcxn",
        opd_address=0,
        opd_always_on=False,
    )

    standard_objects = _standard_objects(mission, node_ids)
    config = _common_config(mission.common['fw'], mission, node_ids)
    _add_standard_objects(config, card, standard_objects)

    return make_od('fw_base', {'fw_base': card}, config)
