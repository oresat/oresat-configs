from argparse import Namespace
from pathlib import Path
from typing import Any

from canopen import ObjectDictionary, export_od

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
    desc = "generate EDS file for OreSat node(s)"
    parser = subparsers.add_parser("eds", description=desc, help=desc)
    parser.set_defaults(func=gen_eds)

    parser.add_argument(
        "--oresat",
        default=Mission.default().arg,
        choices=[m.arg for m in Mission],
        type=lambda x: x.lower().removeprefix("oresat"),
        help="Oresat Mission. (Default: %(default)s)",
    )
    parser.add_argument("card", help="card name; all, c3, gps, star_tracker_1, etc")
    parser.add_argument(
        "-d", "--dir-path", default=".", type=Path, help='Directory path. (Default "%(default)s")'
    )


def gen_eds(args: Namespace) -> None:
    """Gen_eds main."""
    config = OreSatConfig(args.oresat)

    def write_eds(od: ObjectDictionary) -> None:
        file = od.device_information.product_name + ".eds"
        file = file.lower().replace(" ", "_")
        path = args.dir_path / file
        print(f"Writing od to {path}")
        export_od(od, str(path))

    if args.card.lower() == "all":
        for od in config.od_db.values():
            write_eds(od)
    else:
        write_eds(config.od_db[config.name_from_alias(args.card)])
