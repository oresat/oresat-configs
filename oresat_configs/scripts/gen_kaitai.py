import os
from argparse import Namespace
from typing import Any

import canopen
from canopen.objectdictionary import Array, ObjectDictionary, Record
from yaml import dump

from .._yaml_to_od import get_beacon_def, load_od_configs, load_od_db
from ..configs.cards_config import CardsConfig
from ..configs.mission_config import MissionConfig

GEN_KAITAI = "generate beacon kaitai configuration"


def register_subparser(subparsers: Any) -> None:
    """Registers an ArgumentParser as a subcommand of another parser."""
    parser = subparsers.add_parser("kaitai", help=GEN_KAITAI)
    parser.description = GEN_KAITAI
    parser.add_argument("mission_config", help="mission config path")
    parser.add_argument("cards_config", help="cards config path")
    parser.add_argument(
        "-d",
        "--dir-path",
        default=".",
        help="output directory path. (Default: %(default)s)",
    )
    parser.set_defaults(func=gen_kaitai)


CANOPEN_TO_KAITAI_DT = {
    canopen.objectdictionary.BOOLEAN: "b1",
    canopen.objectdictionary.INTEGER8: "s1",
    canopen.objectdictionary.INTEGER16: "s2",
    canopen.objectdictionary.INTEGER32: "s4",
    canopen.objectdictionary.INTEGER64: "s8",
    canopen.objectdictionary.UNSIGNED8: "u1",
    canopen.objectdictionary.UNSIGNED16: "u2",
    canopen.objectdictionary.UNSIGNED32: "u4",
    canopen.objectdictionary.UNSIGNED64: "u8",
    canopen.objectdictionary.VISIBLE_STRING: "str",
    canopen.objectdictionary.REAL32: "f4",
    canopen.objectdictionary.REAL64: "f8",
}


def write_kaitai(
    mission_config: MissionConfig, od: ObjectDictionary, dir_path: str = "."
) -> None:
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

    beacon_def = get_beacon_def(mission_config, od)

    for obj in beacon_def:
        name = (
            "_".join([obj.parent.name, obj.name])
            if isinstance(obj.parent, (Record, Array))
            else obj.name
        )

        new_var = {
            "id": name,
            "type": CANOPEN_TO_KAITAI_DT[obj.data_type],
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

    # Write kaitai to output file
    with open(f"{dir_path}/{mission_config.name}.ksy", "w+") as file:
        dump(kaitai_data, file)


def gen_kaitai(args: Namespace) -> None:
    mission_config = MissionConfig.from_yaml(args.mission_config)
    cards_config = CardsConfig.from_yaml(args.cards_config)
    config_dir = os.path.dirname(args.cards_config)
    od_configs = load_od_configs(cards_config, config_dir)
    od_db = load_od_db(cards_config, od_configs)
    write_kaitai(mission_config, od_db[cards_config.master.name], args.dir_path)
