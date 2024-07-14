"""
SDO transfer script

This scipt act as CANopen master node, allowing it to read and write other
node's Object Dictionaries.
"""

import os
import sys
from argparse import ArgumentParser, Namespace
from typing import Any, Optional, Union

import canopen

from .. import Consts, OreSatConfig

SDO_TRANSFER = "read or write value to a node's object dictionary via SDO transfers"


def build_parser(parser: ArgumentParser) -> ArgumentParser:
    """Configures an ArgumentParser suitable for this script.

    The given parser may be standalone or it may be used as a subcommand in another ArgumentParser.
    """
    parser.description = SDO_TRANSFER
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
        " (e.g. file:data.bin) (Default: %(default)s)",
    )
    parser.add_argument(
        "--oresat",
        default=Consts.default().arg,
        choices=[m.arg for m in Consts],
        type=lambda x: x.lower().removeprefix("oresat"),
        help="Oresat Mission. (Default: %(default)s)",
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
    parser = build_parser(subparsers.add_parser("sdo", help=SDO_TRANSFER))
    parser.set_defaults(func=sdo_transfer)


def sdo_transfer(args: Optional[Namespace] = None) -> None:
    """Read or write data to a node using a SDO."""
    if args is None:
        args = build_parser(ArgumentParser()).parse_args()

    config = OreSatConfig(args.oresat)

    if args.value.startswith("file:"):
        if not os.path.isfile(args.value[5:]):
            print(f"file does not exist {args.value[5:]}")
            sys.exit()

    node_name = args.node.lower()
    od = config.od_db[node_name]

    # connect to CAN network
    network = canopen.Network()
    node = canopen.RemoteNode(od.node_id, od)
    network.add_node(node)
    network.connect(bustype="socketcan", channel=args.bus)

    # validate object exist and make sdo obj
    try:
        if args.subindex == "none":
            obj = od[args.index]
            sdo = node.sdo[args.index]
        else:
            obj = od[args.index][args.subindex]
            sdo = node.sdo[args.index][args.subindex]
    except KeyError as e:
        print(e)
        sys.exit()

    binary_type = [canopen.objectdictionary.OCTET_STRING, canopen.objectdictionary.DOMAIN]

    # send SDO
    try:
        # Type definiton to satisfy mypy, matches canopen.Variable.raw and .phys type
        # While canopen does declare types, it's not fully set up to have outside
        # projects use them?
        value: Union[int, bool, float, str, bytes]
        if args.mode in ["r", "read"]:
            if obj.data_type == binary_type:
                with open(args.value[5:], "wb") as f:
                    f.write(sdo.raw)
                    value = f"binary data written to {args.value[5:]}"
            else:
                value = sdo.phys
            print(value)
        elif args.mode in ["w", "write"]:
            # convert string input to correct data type
            if obj.data_type in canopen.objectdictionary.INTEGER_TYPES:
                value = int(args.value, 16) if args.value.startswith("0x") else int(args.value)
            elif obj.data_type in canopen.objectdictionary.FLOAT_TYPES:
                value = float(args.value)
            elif obj.data_type == canopen.objectdictionary.VISIBLE_STRING:
                value = args.value
            elif obj.data_type in binary_type:  # read in binary data from file
                with open(args.value[5:], "rb") as f:
                    value = f.read()

            if obj.data_type == binary_type:
                sdo.raw = value
            else:
                sdo.phys = value
        else:
            print('invalid mode\nmust be "r", "read", "w", or "write"')
    except (canopen.SdoAbortedError, AttributeError, FileNotFoundError) as e:
        print(e)

    network.disconnect()
