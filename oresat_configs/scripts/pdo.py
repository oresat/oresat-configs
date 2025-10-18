"""Tools for working with PDOs"""

import time
from argparse import Namespace
from typing import Any

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
    desc = "list or receive PDOs from the specified card"
    parser = subparsers.add_parser("pdo", description=desc, help=desc)
    parser.set_defaults(func=pdo_main)

    parser.add_argument(
        "--oresat",
        default=Mission.default().arg,
        choices=[m.arg for m in Mission],
        type=lambda x: x.lower().removeprefix("oresat"),
        help="Oresat Mission. (Default: %(default)s)",
    )
    parser.add_argument("card", help="card name")
    parser.add_argument(
        "--list",
        action="store_true",
        help="list PDOs expected for the particular card",
    )
    parser.add_argument(
        "--bus",
        default="vcan0",
        help="CAN bus to listen on, defaults to %(default)s",
    )


typenames = {
    canopen.objectdictionary.BOOLEAN: "bool",
    canopen.objectdictionary.INTEGER8: "i8",
    canopen.objectdictionary.INTEGER16: "i16",
    canopen.objectdictionary.INTEGER32: "i32",
    canopen.objectdictionary.UNSIGNED8: "u8",
    canopen.objectdictionary.UNSIGNED16: "u16",
    canopen.objectdictionary.UNSIGNED32: "u32",
    canopen.objectdictionary.REAL32: "f32",
    canopen.objectdictionary.VISIBLE_STRING: "str",
    canopen.objectdictionary.OCTET_STRING: "bytes",
    canopen.objectdictionary.UNICODE_STRING: "ustr",
    canopen.objectdictionary.DOMAIN: "domain",
    # canopen.objectdictionary.INTEGER24: 'i24',
    canopen.objectdictionary.REAL64: "f64",
    canopen.objectdictionary.INTEGER64: "i64",
    # canopen.objectdictionary.UNSIGNED24: 'u24',
    canopen.objectdictionary.UNSIGNED64: "u64",
}


def transmission_type(t: int) -> str:
    """Retreives a name for a TPDO Transmission type

    Subindex 2 of a PDO communication parameter record. See CiA-301 table 72.
    """
    if 0 <= t < 0xF0:
        return f"sync ({t})"
    if 0xF0 < t < 0xFB:
        return "reserved"
    if t == 0xFC:
        return "RTR (sync)"
    if t == 0xFD:
        return "RTR (event)"
    if t == 0xFE:
        return "event (mfg)"
    if t == 0xFF:
        return "event (profile)"
    raise ValueError(f"Invalid transmission type 0x{t:X}")


def print_map(m: canopen.pdo.base.Map) -> None:
    """Prints out a received PDO.

    Which from this library means a PDO Mapping
    """
    data = []
    for v in m:
        signed = v.od.data_type in canopen.objectdictionary.SIGNED_TYPES
        value = int.from_bytes(v.get_data(), byteorder="little", signed=signed)
        data.append(f"{v.name}: {value}")
    print(f'{m.cob_id:03X} {m.name} {" ".join(data)}')


def listen(bus: str, node_id: int, od: canopen.ObjectDictionary) -> None:
    """Listens for PDOs from the given node, formats and prints them to stdout"""
    network = canopen.Network()
    network.connect(channel=bus, bustype="socketcan")

    node = network.add_node(node_id, od)
    node.tpdo.read(from_od=True)
    for pdo in node.tpdo.values():
        pdo.add_callback(print_map)
    node.tpdo.subscribe()

    try:
        while True:
            time.sleep(1)
            network.check()
    finally:
        network.disconnect()


def listpdos(node_id: int, od: canopen.ObjectDictionary) -> None:
    """Prints PDO communication and associated mapping parameters for the given node"""

    network = canopen.Network()
    node = network.add_node(node_id, od)
    node.tpdo.read(from_od=True)
    for index, pdo in node.tpdo.items():
        ttype = transmission_type(pdo.trans_type)
        names = " | ".join(f"{m.name} {typenames[m.od.data_type]}" for m in pdo)
        print(f"PDO {index:2} {pdo.cob_id:03X} ({ttype}) => {names}")


def pdo_main(args: Namespace) -> None:
    """The utility for managing PDOs"""

    config = OreSatConfig(args.oresat)
    node_id = config.cards[args.card].node_id
    od = config.od_db[args.card]

    if args.list:
        listpdos(node_id, od)
    else:
        listen(args.bus, node_id, od)
