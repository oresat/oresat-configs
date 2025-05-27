"""Print out a card's objects directory."""

from argparse import ArgumentParser, Namespace
from typing import Any, Optional

import canopen

from .. import Mission, OreSatConfig
from .._yaml_to_od import STR_2_OD_DATA_TYPE

PRINT_OD = "print the object dictionary out to stdout"


def build_parser(parser: ArgumentParser) -> ArgumentParser:
    """Configures an ArgumentParser suitable for this script.

    The given parser may be standalone or it may be used as a subcommand in another ArgumentParser.
    """
    parser.description = PRINT_OD
    parser.add_argument(
        "--oresat",
        default=Mission.default().arg,
        choices=[m.arg for m in Mission],
        type=lambda x: x.lower().removeprefix("oresat"),
        help="Oresat Mission. (Default: %(default)s)",
    )
    parser.add_argument("card", help="card name; c3, gps, star_tracker_1, etc")
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
    parser = build_parser(subparsers.add_parser("od", help=PRINT_OD))
    parser.set_defaults(func=print_od)


def format_default(value: Any) -> str:
    """Format default value based off of python data type."""
    if isinstance(value, int) and not isinstance(value, bool):
        return hex(value)
    if isinstance(value, str):
        return f'"{value}"'
    return str(value)


def print_od(args: Optional[Namespace] = None) -> None:
    """The print-od main"""
    if args is None:
        args = build_parser(ArgumentParser()).parse_args()

    config = OreSatConfig(args.oresat)

    inverted_od_data_types = {}
    for key, value in STR_2_OD_DATA_TYPE.items():
        inverted_od_data_types[value] = key

    arg_card = args.card.lower().replace("-", "_")

    od = config.od_db[arg_card]
    for i in od:
        if isinstance(od[i], canopen.objectdictionary.Variable):
            data_type = inverted_od_data_types[od[i].data_type]
            value = format_default(od[i].default)
            print(f"0x{i:04X}: {od[i].name} - {data_type} - {value}")
        else:
            print(f"0x{i:04X}: {od[i].name}")
            for j in od[i]:
                data_type = inverted_od_data_types[od[i][j].data_type]
                value = format_default(od[i][j].default)
                print(f"  0x{i:04X} 0x{j:02X}: {od[i][j].name} - {data_type} - {value}")
