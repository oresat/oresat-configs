"""Print out a card's objects directory."""

from argparse import Namespace
from typing import Any

from canopen.objectdictionary import DeviceInformation, ODVariable

from .. import Mission, OreSatConfig
from ..card_config import DATA_TYPE_DEFAULTS


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
    parser.add_argument(
        "-v", '--verbose', action='store_true', help="print all OD entry attributes"
    )


def format_default(value: Any) -> str:
    """Format default value based off of python data type."""
    if isinstance(value, int) and not isinstance(value, bool):
        return hex(value)
    if isinstance(value, str):
        return f'"{value}"'
    return str(value)


def print_attributes(entry: ODVariable) -> None:
    print(f"    unit: {entry.unit}")
    print(f"    factor: {entry.factor}")
    print(f"    min: {entry.min}")
    print(f"    max: {entry.max}")
    print(f"    default: {entry.default}")
    print(f"    relative: {entry.relative}")
    print(f"    access_type: {entry.access_type}")
    print("    value descriptions:")
    for value, descr in entry.value_descriptions.items():
        print(f"      {value}: {descr}")
    print("    bit definitions:")
    for definition, bits in entry.bit_definitions.items():
        print(f"      {definition}: {bits}")
    print(f"    storage_location: {entry.storage_location}")
    print(f"    pdo_mappable: {entry.pdo_mappable}")


def print_device_info(dev: DeviceInformation) -> None:
    print(f"    allowed baudrates:          {dev.allowed_baudrates}")
    print(f"    vendor name:                {dev.vendor_name}")
    print(f"    vendor number:              {dev.vendor_number}")
    print(f"    product name:               {dev.product_name}")
    print(f"    product number:             {dev.product_number}")
    print(f"    revision number:            {dev.revision_number}")
    print(f"    order code:                 {dev.order_code}")
    print(f"    simple boot up master:      {dev.simple_boot_up_master}")
    print(f"    simple boot up slave:       {dev.simple_boot_up_slave}")
    print(f"    granularity:                {dev.granularity}")
    print(f"    dynamic channels supported: {dev.dynamic_channels_supported}")
    print(f"    group messaging:            {dev.group_messaging}")
    print(f"    nr of RXPDO:                {dev.nr_of_RXPDO}")
    print(f"    nr of TXPDO:                {dev.nr_of_TXPDO}")
    print(f"    LSS supported:              {dev.LSS_supported}")


def print_od(args: Namespace) -> None:
    """The print-od main"""
    config = OreSatConfig(args.oresat)

    inverted_od_data_types = {dt.od_type: name for name, dt in DATA_TYPE_DEFAULTS.items()}

    arg_card = args.card.lower().replace("-", "_")

    od = config.od_db[arg_card]

    if args.verbose:
        print(arg_card)
        print('bitrate:', od.bitrate)
        print('node id:', od.node_id)
        print_device_info(od.device_information)

    for i, entry in od.items():
        if isinstance(entry, ODVariable):
            assert entry.data_type is not None
            data_type = inverted_od_data_types[entry.data_type]
            value = format_default(entry.default)
            print(f"0x{i:04X}: {entry.name} - {data_type} - {value} - {entry.description}")
            if args.verbose:
                print_attributes(entry)

        else:
            print(f"0x{i:04X}: {entry.name}: {entry.description}")
            for j, subentry in entry.items():
                data_type = inverted_od_data_types[subentry.data_type]
                value = format_default(subentry.default)
                descr = f"{data_type} - {value} - {subentry.description}"
                print(f"  0x{i:04X} 0x{j:02X}: {subentry.name} - {descr}")
                if args.verbose:
                    print_attributes(subentry)
