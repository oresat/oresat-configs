"""Prints the known list of oresat cards"""

from argparse import ArgumentParser, Namespace, RawDescriptionHelpFormatter
from collections import defaultdict
from dataclasses import asdict, fields
from typing import Any, Optional

from tabulate import tabulate

from ..card_info import Card, cards_from_csv
from ..constants import Mission

LIST_CARDS = "list oresat cards, suitable as arguments to other commands"


def build_parser(parser: ArgumentParser) -> ArgumentParser:
    """Configures an ArgumentParser suitable for this script.

    The given parser may be standalone or it may be used as a subcommand in another ArgumentParser.
    """
    parser.description = LIST_CARDS
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
    parser = build_parser(subparsers.add_parser("cards", help=LIST_CARDS))
    parser.set_defaults(func=list_cards)


def list_cards(args: Optional[Namespace] = None) -> None:
    """Lists oresat cards and their configurations"""
    if args is None:
        args = build_parser(ArgumentParser()).parse_args()

    with Mission.from_string(args.oresat).cards as path:
        cards = cards_from_csv(path)
    data: dict[str, list[str]] = defaultdict(list)
    data["name"] = list(cards)
    for card in cards.values():
        for key, value in asdict(card).items():
            if key == "node_id":
                value = f"0x{value:02X}" if value else ""
            elif key == "opd_address":
                value = f"0x{value:02X}" if value else ""
            elif key == "opd_always_on":
                value = "True" if value else ""
            elif key in ("common", "config"):
                continue
            data[key].append(value)
    print(tabulate(data, headers="keys"))
