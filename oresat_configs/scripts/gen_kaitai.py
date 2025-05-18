from __future__ import annotations

from pathlib import Path
from typing import Any

from canopen.objectdictionary import Array, ObjectDictionary, Record
from yaml import dump

from .._yaml_to_od import DataType, get_beacon_def, load_od_configs, load_od_db
from ..configs.cards_config import CardsConfig
from ..configs.mission_config import MissionConfig

CANOPEN_TO_KAITAI_DT = {
    DataType.BOOL: "b1",
    DataType.INT8: "s1",
    DataType.INT16: "s2",
    DataType.INT32: "s4",
    DataType.INT64: "s8",
    DataType.UINT8: "u1",
    DataType.UINT16: "u2",
    DataType.UINT32: "u4",
    DataType.UINT64: "u8",
    DataType.STR: "str",
    DataType.FLOAT32: "f4",
    DataType.FLOAT64: "f8",
}


def write_kaitai(
    mission_config: MissionConfig, od: ObjectDictionary, dir_path: str | Path | None = None
) -> None:
    if dir_path is None:
        dir_path = Path().cwd()
    elif isinstance(dir_path, str):
        dir_path = Path(dir_path)

    #  Setup pre-determined canned types
    kaitai_data: Any = {
        "meta": {
            "id": mission_config.name,
            "title": f"{mission_config.nice_name} Decoder Struct",
            "endian": "le",
        },
        "seq": [
            {
                "id": "ax25_frame",
                "type": "ax25_frame",
                "doc-ref": "https://www.tapr.org/pub_ax25.html",
            }
        ],
        "types": {
            "ax25_frame": {
                "seq": [
                    {
                        "id": "ax25_header",
                        "type": "ax25_header",
                    },
                    {
                        "id": "payload",
                        "type": {
                            "switch-on": "ax25_header.ctl & 0x13",
                            "cases": {
                                "0x03": "ui_frame",
                                "0x13": "ui_frame",
                                "0x00": "i_frame",
                                "0x02": "i_frame",
                                "0x10": "i_frame",
                                "0x12": "i_frame",
                            },
                        },
                    },
                    {
                        "id": "ax25_trunk",
                        "type": "ax25_trunk",
                    },
                ]
            },
            "ax25_header": {
                "seq": [
                    {"id": "dest_callsign_raw", "type": "callsign_raw"},
                    {"id": "dest_ssid_raw", "type": "ssid_mask"},
                    {"id": "src_callsign_raw", "type": "callsign_raw"},
                    {"id": "src_ssid_raw", "type": "ssid_mask"},
                    {
                        "id": "repeater",
                        "type": "repeater",
                        "if": "(src_ssid_raw.ssid_mask & 0x01) == 0",
                        "doc": "Repeater flag is set!",
                    },
                    {"id": "ctl", "type": "u1"},
                ],
            },
            "ax25_trunk": {
                "seq": [
                    {
                        "id": "refcs",
                        "type": "u4",
                    }
                ]
            },
            "repeater": {
                "seq": [
                    {
                        "id": "rpt_instance",
                        "type": "repeaters",
                        "repeat": "until",
                        "repeat-until": "((_.rpt_ssid_raw.ssid_mask & 0x1) == 0x1)",
                        "doc": "Repeat until no repeater flag is set!",
                    }
                ]
            },
            "repeaters": {
                "seq": [
                    {
                        "id": "rpt_callsign_raw",
                        "type": "callsign_raw",
                    },
                    {
                        "id": "rpt_ssid_raw",
                        "type": "ssid_mask",
                    },
                ]
            },
            "callsign_raw": {
                "seq": [
                    {
                        "id": "callsign_ror",
                        "process": "ror(1)",
                        "size": 6,
                        "type": "callsign",
                    }
                ]
            },
            "callsign": {
                "seq": [
                    {
                        "id": "callsign",
                        "type": "str",
                        "encoding": "ASCII",
                        "size": 6,
                        "valid": {"any-of": ['"KJ7SAT"', '"SPACE "']},
                    }
                ]
            },
            "ssid_mask": {
                "seq": [
                    {
                        "id": "ssid_mask",
                        "type": "u1",
                    }
                ],
                "instances": {"ssid": {"value": "(ssid_mask & 0x0f) >> 1"}},
            },
            "i_frame": {
                "seq": [
                    {
                        "id": "pid",
                        "type": "u1",
                    },
                    {"id": "ax25_info", "type": "ax25_info_data", "size": -1},
                ]
            },
            "ui_frame": {
                "seq": [
                    {
                        "id": "pid",
                        "type": "u1",
                    },
                    {"id": "ax25_info", "type": "ax25_info_data", "size": -1},
                ]
            },
            "ax25_info_data": {"seq": []},
        },
    }

    # Append field types for each field
    payload_size = 0

    beacon_def = get_beacon_def(od, mission_config)

    for obj in beacon_def:
        name = (
            f"{obj.parent.name}_{obj.name}" if isinstance(obj.parent, (Record, Array)) else obj.name
        )

        new_var = {
            "id": name,
            "type": CANOPEN_TO_KAITAI_DT[DataType(obj.data_type)],
            "doc": obj.description,
        }
        if new_var["type"] == "str":
            new_var["encoding"] = "ASCII"
            if obj.access_type == "const":
                new_var["size"] = len(obj.default)
            payload_size += new_var["size"] * 8
        else:
            payload_size += len(obj)

        kaitai_data["types"]["ax25_info_data"]["seq"].append(new_var)

    payload_size //= 8
    kaitai_data["types"]["i_frame"]["seq"][1]["size"] = payload_size
    kaitai_data["types"]["ui_frame"]["seq"][1]["size"] = payload_size

    file_path = dir_path / f"{mission_config.name}.ksy"
    with file_path.open("w+") as f:
        dump(kaitai_data, f)


def gen_kaitai(
    cards_config_path: str | Path, mission_config_paths: str | Path | list[str | Path]
) -> None:
    if isinstance(cards_config_path, str):
        cards_config_path = Path(cards_config_path)
    cards_config = CardsConfig.from_yaml(cards_config_path)

    if isinstance(mission_config_paths, (str, Path)):
        mission_config_paths = [mission_config_paths]
    mission_configs = [MissionConfig.from_yaml(m) for m in mission_config_paths]

    config_dir = cards_config_path.parent
    od_configs = load_od_configs(cards_config, config_dir)
    od_db = load_od_db(cards_config, od_configs)
    for mission_config in mission_configs:
        write_kaitai(mission_config, od_db[cards_config.manager.name])
