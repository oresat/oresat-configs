"""
SDO transfer script

This scipt act as CANopen master node, allowing it to read and write other
node's Object Dictionaries.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from argparse import Namespace

import canopen
from canopen.objectdictionary import (
    BOOLEAN,
    DOMAIN,
    FLOAT_TYPES,
    INTEGER_TYPES,
    OCTET_STRING,
    UNICODE_STRING,
    VISIBLE_STRING,
)
from canopen.sdo import SdoArray, SdoRecord

from .. import Mission, OreSatConfig

STRING_TYPES = (VISIBLE_STRING, UNICODE_STRING)
BINARY_TYPES = (OCTET_STRING, DOMAIN)


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
    desc = "read or write value to a node's object dictionary via SDO transfers"
    parser = subparsers.add_parser("sdo", description=desc, help=desc)
    parser.set_defaults(func=sdo_transfer)

    parser.add_argument("bus", metavar="BUS", help="CAN bus to use (e.g., can0, vcan0)")
    parser.add_argument("node", metavar="NODE", help="device node name (e.g. gps, solar_module_1)")
    parser.add_argument("mode", metavar="MODE", help="r[ead] or w[rite] (e.g. r, read, w, write)")
    parser.add_argument("index", metavar="INDEX", help="object dictionary index")
    parser.add_argument("subindex", metavar="SUBINDEX", help='object dictionary subindex or "none"')
    parser.add_argument(
        "value",
        metavar="VALUE",
        nargs="?",
        default="",
        help="Data to write or for only octet/domain data types a path to a file (e.g. data.bin).",
    )
    parser.add_argument(
        "--oresat",
        default=Mission.default().arg,
        choices=[m.arg for m in Mission],
        type=lambda x: x.lower().removeprefix("oresat"),
        help="Oresat Mission. (Default: %(default)s)",
    )


def sdo_transfer(args: Namespace) -> None:
    """Read or write data to a node using a SDO."""
    config = OreSatConfig(args.oresat)
    od = config.od_db[args.node.lower()]
    node = canopen.RemoteNode(0, od)

    if args.mode in ["r", "read"]:
        mode = 'read'
    elif args.mode in ["w", "write"]:
        mode = 'write'
    else:
        print('Invalid mode: must be "r", "read", "w", or "write"')
        return

    # validate object exist and make sdo obj
    try:
        sdo = node.sdo[args.index]
        if isinstance(sdo, (SdoRecord, SdoArray)):
            sdo = sdo[args.subindex]
    except KeyError as e:
        print(e)
        return

    if sdo.od.data_type in BINARY_TYPES:
        file = Path(args.value)

    if mode == 'write':
        # FIXME: Type definiton to satisfy mypy, matches canopen.Variable.raw and .phys type
        # While canopen does declare types, it's not fully set up to have outside
        # projects use them?
        value: int | bool | float | str | bytes

        # convert string input to correct data type
        if sdo.od.data_type == BOOLEAN:
            value = bool(args.value)
        elif sdo.od.data_type in INTEGER_TYPES:
            value = int(args.value, 0)
        elif sdo.od.data_type in FLOAT_TYPES:
            value = float(args.value)
        elif sdo.od.data_type == STRING_TYPES:
            value = args.value
        elif sdo.od.data_type in BINARY_TYPES:  # read in binary data from file
            with file.open("rb") as f:
                value = f.read()

    # connect to CAN network
    network = canopen.Network()
    network.add_node(node)
    with network.connect(bustype="socketcan", channel=args.bus):
        # send SDO
        try:
            if mode == "read":
                if sdo.od.data_type in BINARY_TYPES:
                    with file.open("wb") as f:
                        f.write(sdo.raw)
                        print(f"binary data written to {file}")
                else:
                    print(sdo.phys)
            elif mode == "write":
                if sdo.od.data_type in BINARY_TYPES:
                    sdo.raw = value
                else:
                    sdo.phys = value
        except (canopen.SdoAbortedError, FileNotFoundError) as e:
            print(e)
