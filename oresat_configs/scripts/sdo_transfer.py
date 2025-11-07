"""
SDO transfer script

This scipt act as CANopen master node, allowing it to read and write other
node's Object Dictionaries.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from argparse import Namespace

import canopen

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
        help="Data to write or for only octet/domain data types a path to a file."
        " (e.g. file:data.bin)",
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

    if args.value.startswith("file:") and not os.path.isfile(args.value[5:]):
        print(f"file does not exist {args.value[5:]}")
        return

    node_name = args.node.lower()
    od = config.od_db[node_name]

    # connect to CAN network
    network = canopen.Network()
    node = canopen.RemoteNode(0, od)
    network.add_node(node)
    network.connect(bustype="socketcan", channel=args.bus)

    # validate object exist and make sdo obj
    try:
        if args.subindex == "none":
            sdo = node.sdo[args.index]
        else:
            sdo = node.sdo[args.index][args.subindex]
    except KeyError as e:
        print(e)
        return

    binary_type = [canopen.objectdictionary.OCTET_STRING, canopen.objectdictionary.DOMAIN]

    # send SDO
    try:
        # FIXME: Type definiton to satisfy mypy, matches canopen.Variable.raw and .phys type
        # While canopen does declare types, it's not fully set up to have outside
        # projects use them?
        value: int | bool | float | str | bytes
        if args.mode in ["r", "read"]:
            if sdo.od.data_type in binary_type:
                with open(args.value[5:], "wb") as f:
                    f.write(sdo.raw)
                    value = f"binary data written to {args.value[5:]}"
            else:
                value = sdo.phys
            print(value)
        elif args.mode in ["w", "write"]:
            # convert string input to correct data type
            if sdo.od.data_type in canopen.objectdictionary.INTEGER_TYPES:
                value = int(args.value, 16) if args.value.startswith("0x") else int(args.value)
            elif sdo.od.data_type in canopen.objectdictionary.FLOAT_TYPES:
                value = float(args.value)
            elif sdo.od.data_type == canopen.objectdictionary.VISIBLE_STRING:
                value = args.value
            elif sdo.od.data_type in binary_type:  # read in binary data from file
                with open(args.value[5:], "rb") as f:
                    value = f.read()

            if sdo.od.data_type in binary_type:
                sdo.raw = value
            else:
                sdo.phys = value
        else:
            print('invalid mode\nmust be "r", "read", "w", or "write"')
    except (canopen.SdoAbortedError, FileNotFoundError) as e:
        print(e)

    network.disconnect()
