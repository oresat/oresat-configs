"""Print out a card's objects directory."""

from argparse import Namespace
from typing import Any

import canopen

from .. import Mission, OreSatConfig
from .._yaml_to_od import STR_2_OD_DATA_TYPE


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
    desc = "print the object dictionary out to stdout"
    parser = subparsers.add_parser("od", description=desc, help=desc)
    parser.set_defaults(func=print_od)

    parser.add_argument(
        "--oresat",
        default=Mission.default().arg,
        choices=[m.arg for m in Mission],
        type=lambda x: x.lower().removeprefix("oresat"),
        help="Oresat Mission. (Default: %(default)s)",
    )
    parser.add_argument("card", help="card name; c3, gps, star_tracker_1, etc")


def format_default(value: Any) -> str:
    """Format default value based off of python data type."""
    if isinstance(value, int) and not isinstance(value, bool):
        return hex(value)
    if isinstance(value, str):
        return f'"{value}"'
    return str(value)


def print_od(args: Namespace) -> None:
    """The print-od main"""
    config = OreSatConfig(args.oresat)

    inverted_od_data_types = {datatype: name for name, datatype in STR_2_OD_DATA_TYPE.items()}

    arg_card = args.card.lower().replace("-", "_")

    od = config.od_db[arg_card]
    for i, entry in od.items():
        if isinstance(entry, canopen.objectdictionary.Variable):
            assert entry.data_type is not None
            data_type = inverted_od_data_types[entry.data_type]
            value = format_default(entry.default)
            print(f"0x{i:04X}: {entry.name} - {data_type} - {value}")
        else:
            print(f"0x{i:04X}: {entry.name}")
            for j, subentry in entry.items():
                data_type = inverted_od_data_types[subentry.data_type]
                value = format_default(subentry.default)
                print(f"  0x{i:04X} 0x{j:02X}: {subentry.name} - {data_type} - {value}")
