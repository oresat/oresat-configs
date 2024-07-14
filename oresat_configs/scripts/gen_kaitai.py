"""Generate KaiTai for the beacon."""

from argparse import ArgumentParser, Namespace
from typing import Any, Optional, cast

import canopen
from yaml import dump

from .. import Consts, OreSatConfig

GEN_KAITAI = "generate beacon kaitai configuration"


def build_parser(parser: ArgumentParser) -> ArgumentParser:
    """Configures an ArgumentParser suitable for this script.

    The given parser may be standalone or it may be used as a subcommand in another ArgumentParser.
    """
    parser.description = GEN_KAITAI
    parser.add_argument(
        "--oresat",
        default=Consts.default().arg,
        choices=[m.arg for m in Consts],
        type=lambda x: x.lower().removeprefix("oresat"),
        help="Oresat Mission. (Default: %(default)s)",
    )
    parser.add_argument(
        "-d", "--dir-path", default=".", help="Output directory path. (Default: %(default)s)"
    )
    return parser


def register_subparser(subparsers: Any) -> None:
    """Registers an ArgumentParser as a subcommand of another parser.

    Intended to be called by __main__.py for each script. Given the output of add_subparsers(),
    (which I think is a subparser group, but is technically unspecified) this function should
    create its own ArgumentParser via add_parser(). It must also set_default() the func argument
    to designate the entry point into this script.
    See https://docs.python.org/3/library/argparse.html#sub-commands, especially the end of that
    section, for more.
    """
    parser = build_parser(subparsers.add_parser("xtce", help=GEN_KAITAI))
    parser.set_defaults(func=GEN_KAITAI)


CANOPEN_TO_KAITAI_DT = {
    canopen.objectdictionary.BOOLEAN: "s",
    canopen.objectdictionary.INTEGER8: "int8",
    canopen.objectdictionary.INTEGER16: "i1",
    canopen.objectdictionary.INTEGER32: "i2",
    canopen.objectdictionary.INTEGER64: "i3",
    canopen.objectdictionary.UNSIGNED8: "u1",
    canopen.objectdictionary.UNSIGNED16: "u2",
    canopen.objectdictionary.UNSIGNED32: "u3",
    canopen.objectdictionary.UNSIGNED64: "u4",
    canopen.objectdictionary.VISIBLE_STRING: "str",
    canopen.objectdictionary.REAL32: "float",
    canopen.objectdictionary.REAL64: "double",
}


def write_kaitai(config: OreSatConfig, dir_path: str = ".") -> None:
    """Write beacon configs to a kaitai file."""

    # Grab and format mission name
    name = config.mission.name.lower().replace("_", ".")

    #  Setup pre-determined canned types
    kaitai_data = {
        "meta": {
            "id": name,
            "title": f"{name} Decoder Struct",
            "endian": "le",
        },
        "doc": "",
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
                                "0x12": "i_framec",
                            },
                        },
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
            "repeater": {
                "seq": [
                    {
                        "id": "rpt_instance",
                        "type": "repeaters",
                        "repeat": "until",
                        "repeat-until": "until",
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
                        "process": "repeaters",
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
                    {"id": "ax25_info", "type": "ax25_info_data", "size-eos": True},
                ]
            },
            "ui_frame": {
                "seq": [
                    {
                        "id": "pid",
                        "type": "u1",
                    },
                    {"id": "ax25_info", "type": "ax25_info_data", "size-eos": True},
                ]
            },
            "ax25_info_data": {"seq": []},
        },
    }

    # Append field types for each field
    for obj in config.beacon_def:
        new_var = {
            "id": obj.name,
            "type": CANOPEN_TO_KAITAI_DT[obj.data_type],
            "doc": obj.description,
        }
        if new_var["type"] == "str":
            new_var["encoding"] = "ASCII"
            if obj.access_type == "const":
                new_var["size"] = len(obj.default)

        cast(
            Any, cast(Any, cast(Any, kaitai_data.get("types")).get("ax25_info_data")).get("seq")
        ).append(
            new_var
        )  # Same as: `kaitai_data["types"]["ax25_info_data"]["seq"].append(new_var)`D

    # Write kaitai to output file
    with open(f"{dir_path}/{name}.ksy", "w+") as file:
        dump(kaitai_data, file)


def gen_kaitai(args: Optional[Namespace] = None) -> None:
    """Gen_kaitai main."""
    if args is None:
        args = build_parser(ArgumentParser()).parse_args()

    config = OreSatConfig(args.oresat)
    write_kaitai(config, args.dir_path)
