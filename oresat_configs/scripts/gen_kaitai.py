"""Generate KaiTai for the beacon."""

from argparse import Namespace
from typing import Any, cast

import canopen
from canopen.objectdictionary import Array, Record
from yaml import dump

from .. import Mission, OreSatConfig


def build_arguments(subparsers: Any) -> None:
    """Build command line arguments for this script.

    This function will be invoked by scripts.main to configure command line arguments for this
    subcommand. Use subparsers.add_parser() to get an ArgumentParser. The parser must have the
    default argument func which is the entry point for this subcommand: parser.set_defaults(func=?)

    Parameters
    ----------
    subparsers
        The output of ArgumentParser.add_subparsers() from the primary ArgumentParser. This function
        should call add_parser() on this parameter to get the ArgumentParser that is used to
        configure arguments for this subcommand.
        See https://docs.python.org/3/library/argparse.html#sub-commands, especially the end of
        that section, for more.
    """
    desc = "generate beacon kaitai configuration"
    parser = subparsers.add_parser("kaitai", description=desc, help=desc)
    parser.set_defaults(func=gen_kaitai)

    parser.add_argument(
        "--oresat",
        default=Mission.default().arg,
        choices=[m.arg for m in Mission],
        type=lambda x: x.lower().removeprefix("oresat"),
        help="Oresat Mission. (Default: %(default)s)",
    )
    parser.add_argument(
        "-d",
        "--dir-path",
        default=".",
        help="Output directory path. (Default: %(default)s)",
    )


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


def write_kaitai(config: OreSatConfig, dir_path: str = ".") -> None:
    """Write beacon configs to a kaitai file."""

    # Grab and format mission name
    filename = config.mission.filename()

    #  Setup pre-determined canned types
    kaitai_data: Any = {
        "meta": {
            "id": filename,
            "title": f"{filename} Decoder Struct",
            "endian": "le",
        },
        "seq": [
            {
                "id": "ax25_frame",
                "type": "ax25_frame",
                "doc-ref": "https://www.tapr.org/pub_ax25.html",
            },
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
                ],
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
                    },
                ],
            },
            "repeater": {
                "seq": [
                    {
                        "id": "rpt_instance",
                        "type": "repeaters",
                        "repeat": "until",
                        "repeat-until": "((_.rpt_ssid_raw.ssid_mask & 0x1) == 0x1)",
                        "doc": "Repeat until no repeater flag is set!",
                    },
                ],
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
                ],
            },
            "callsign_raw": {
                "seq": [
                    {
                        "id": "callsign_ror",
                        "process": "ror(1)",
                        "size": 6,
                        "type": "callsign",
                    },
                ],
            },
            "callsign": {
                "seq": [
                    {
                        "id": "callsign",
                        "type": "str",
                        "encoding": "ASCII",
                        "size": 6,
                        "valid": {"any-of": ['"KJ7SAT"', '"SPACE "']},
                    },
                ],
            },
            "ssid_mask": {
                "seq": [
                    {
                        "id": "ssid_mask",
                        "type": "u1",
                    },
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
                ],
            },
            "ui_frame": {
                "seq": [
                    {
                        "id": "pid",
                        "type": "u1",
                    },
                    {"id": "ax25_info", "type": "ax25_info_data", "size": -1},
                ],
            },
            "ax25_info_data": {"seq": []},
        },
    }

    # Append field types for each field
    payload_size = 0

    for obj in config.beacon_def:
        name = (
            f"{obj.parent.name}_{obj.name}" if isinstance(obj.parent, (Record, Array)) else obj.name
        )
        assert obj.data_type is not None
        new_var: dict[str, Any] = {
            "id": name,
            "type": CANOPEN_TO_KAITAI_DT[obj.data_type],
            "doc": obj.description,
        }
        if new_var["type"] == "str":
            new_var["encoding"] = "ASCII"
            if obj.access_type == "const":
                new_var["size"] = len(cast(str, obj.default))
            payload_size += new_var["size"] * 8
        else:
            payload_size += len(obj)

        kaitai_data["types"]["ax25_info_data"]["seq"].append(new_var)

    payload_size //= 8
    kaitai_data["types"]["i_frame"]["seq"][1]["size"] = payload_size
    kaitai_data["types"]["ui_frame"]["seq"][1]["size"] = payload_size

    # Write kaitai to output file
    with open(f"{dir_path}/{filename}.ksy", "w+") as file:
        dump(kaitai_data, file)


def gen_kaitai(args: Namespace) -> None:
    """Gen_kaitai main."""
    config = OreSatConfig(args.oresat)
    write_kaitai(config, args.dir_path)
