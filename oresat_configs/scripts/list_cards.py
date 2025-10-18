"""Prints the known list of oresat cards"""

from argparse import Namespace, RawDescriptionHelpFormatter
from collections import defaultdict
from dataclasses import asdict, fields
from importlib.resources import as_file
from typing import Any

from tabulate import tabulate

from ..card_info import Card, cards_from_csv
from ..constants import Mission


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
    desc = "list oresat cards, suitable as arguments to other commands"
    parser = subparsers.add_parser("cards", description=desc, help=desc)
    parser.set_defaults(func=list_cards)

    parser.formatter_class = RawDescriptionHelpFormatter
    parser.add_argument(
        "--oresat",
        default=Mission.default().arg,
        choices=[m.arg for m in Mission],
        type=lambda x: x.lower().removeprefix("oresat"),
        help="Oresat Mission. (Default: %(default)s)",
    )
    # I'd like to pull the descriptions directly out of Card but attribute docstrings are discarded
    # and not accessable at runtime.
    rows = [
        ["name", "The canonical name, suitable for arguments of other scripts"],
        ["nice_name", "A nice name for the card"],
        ["node_id", "CANopen node id"],
        ["processor", 'Processor type; e.g.: "octavo", "stm32", or "none"'],
        ["opd_address", "OPD address"],
        ["opd_always_on", "Keep the card on all the time. Only for battery cards"],
        ["child", "Optional child node name. Useful for CFC cards."],
    ]
    parser.epilog = "Columns:\n" + tabulate(rows)
    missing = {f.name for f in fields(Card)} - {r[0] for r in rows}
    if missing:
        parser.epilog += f"\nColums missing description: {missing}"


def list_cards(args: Namespace) -> None:
    """Lists oresat cards and their configurations"""

    with as_file(Mission.from_string(args.oresat).cards) as path:
        cards = cards_from_csv(path)
    data: dict[str, list[str]] = defaultdict(list)
    data["name"] = list(cards)
    for card in cards.values():
        for key, value in asdict(card).items():
            if key in {"node_id", "opd_address"}:
                value = f"0x{value:02X}" if value else ""
            elif key == "opd_always_on":
                value = "True" if value else ""
            elif key in ("common", "config"):
                continue
            data[key].append(value)
    print(tabulate(data, headers="keys"))
