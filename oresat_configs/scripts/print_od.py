"""Print out a card's objects directory."""

import sys
from argparse import ArgumentParser, Namespace
from typing import Any, Optional

import canopen

from .. import OreSatConfig, OreSatId
from .._yaml_to_od import OD_DATA_TYPES

PRINT_OD = "print the object dictionary out to stdout"
PRINT_OD_PROG = "oresat-print-od"


def build_parser(parser: ArgumentParser) -> ArgumentParser:
    """Configures an ArgumentParser suitable for this script.

    The given parser may be standalone or it may be used as a subcommand in another ArgumentParser.
    """
    parser.description = PRINT_OD
    parser.add_argument("oresat", default="oresat0", help="oresat mission; oresat0 or oresat0.5")
    parser.add_argument("card", help="card name; c3, gps, star_tracker_1, etc")
    return parser


def register_subparser(subparsers):
    """Registers an ArgumentParser as a subcommand of another parser.

    Intended to be called by __main__.py for each script. Given the output of add_subparsers(),
    (which I think is a subparser group, but is technically unspecified) this function should
    create its own ArgumentParser via add_parser(). It must also set_default() the func argument
    to designate the entry point into this script.
    See https://docs.python.org/3/library/argparse.html#sub-commands, especially the end of that
    section, for more.
    """
    parser = build_parser(subparsers.add_parser(PRINT_OD_PROG, help=PRINT_OD))
    parser.set_defaults(func=print_od)


def format_default(value: Any) -> str:
    """Format default value based off of python data type."""
    if isinstance(value, int) and not isinstance(value, bool):
        value = hex(value)
    elif isinstance(value, str):
        value = f'"{value}"'
    return value


def print_od(args: Optional[Namespace] = None):
    """The print-od main"""
    if args is None:
        args = build_parser(ArgumentParser()).parse_args()

    arg_oresat = args.oresat.lower()
    if arg_oresat in ["0", "oresat0"]:
        oresat_id = OreSatId.ORESAT0
    elif arg_oresat in ["0.5", "oresat0.5"]:
        oresat_id = OreSatId.ORESAT0_5
    elif arg_oresat in ["1", "oresat1"]:
        oresat_id = OreSatId.ORESAT1
    else:
        print(f"invalid oresat mission: {args.oresat}")
        sys.exit()

    config = OreSatConfig(oresat_id)

    inverted_od_data_types = {}
    for key, value in OD_DATA_TYPES.items():
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
