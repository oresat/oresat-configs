from argparse import Namespace
from pathlib import Path
from typing import Any

from canopen import ObjectDictionary, export_od
from canopen.objectdictionary import ODArray, ODVariable
from canopen.objectdictionary.datatypes import OCTET_STRING, UNSIGNED8, UNSIGNED32

from .. import Mission, OreSatConfig
from ..card_config import Rpdo


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
        if od.device_information.product_name is None:
            raise SystemExit("OD incomplete (missing product name)")
        fixup_od(od)
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


def fixup_od(od: ObjectDictionary) -> None:
    '''Fixes to our OD to support EDSEditor/CANopenNode 1.3/2.0.'''
    d = od.device_information
    if d.nr_of_RXPDO is None:
        raise SystemExit("OD incomplete (missing RXPDO count)")

    # For the canopen-python eds generator it expets baud instead of kilobaud
    d.allowed_baudrates = {1000 * baud for baud in d.allowed_baudrates}
    # CANopenNode needs at least one RPDO to compile so we point at a
    # random object and then disable the PDO.
    if d.nr_of_RXPDO < 1:
        rpdo = Rpdo(num=1, card='', tpdo_num=1, fields=[['scet']])
        mp = rpdo.to_mapping_parameter(od)
        mp[0].value = 0
        od.add_object(mp)
        od.add_object(rpdo.to_communication_parameter(0))
        # upstream type annotation is obviuosly incorrect - marked as optional[bool] for a number?
        d.nr_of_RXPDO = 1  # type: ignore[assignment]

    # EDSEditor expects a bunch of objects to be named in a specific way
    pdo_mappings = []
    for index, obj in od.items():
        if index == 0x1001:
            obj.name = "Error register"
        elif index == 0x1003:
            obj.name = "Pre-defined error field"
        elif index == 0x1005:
            obj.name = "COB_ID_SYNCMessage"
        elif index == 0x1006:
            obj.name = "Communication Cycle Period"
        elif index == 0x1015:
            obj.name = "Inhibit time EMCY"
        elif index == 0x1017:
            obj.name = "Producer heartbeat time"
        elif index == 0x1018:
            for subindex, subobj in obj.items():
                if subindex == 0x01:
                    subobj.name = "vendorID"
                elif subindex == 0x02:
                    subobj.name = "productCode"
                elif subindex == 0x03:
                    subobj.name = "revisionNumber"
                elif subindex == 0x04:
                    subobj.name = "serialNumber"
        elif 0x1200 <= index < 0x1300:
            obj.name = "SDO server parameter"
            for subindex, subobj in obj.items():
                if subindex == 0x01:
                    subobj.name = "COB_IDClientToServer"
                elif subindex == 0x02:
                    subobj.name = "COB_IDServerToClient"
        elif 0x1400 <= index < 0x1600:
            obj.name = "RPDOCommunicationParameter"
        elif 0x1600 <= index < 0x1800:
            obj.name = "RPDOMappingParameter"
            pdo_mappings.append(obj)
        elif 0x1800 <= index < 0x1A00:
            obj.name = "TPDOCommunicationParameter"
        elif 0x1A00 <= index < 0x1C00:
            obj.name = "TPDOMappingParameter"
            pdo_mappings.append(obj)

    # CANopenNode 1.3/2.0 expects all the Mapping Parameters to be length 8 for each PDO
    for obj in pdo_mappings:
        for subindex in range(1, 8 + 1):
            if subindex not in obj:
                map_obj = ODVariable(f"mapping_object_{subindex}", obj.index, subindex)
                map_obj.data_type = UNSIGNED32
                map_obj.value = 0
                map_obj.default = 0
                obj.add_member(map_obj)

    # There's a bunch of manditory "optional" objects that CANOpenNode 1.3/2.0 expects, here we
    # define them all in their disabled setting.
    sync_win = ODVariable("Synchronous window length", 0x1007)
    sync_win.data_type = UNSIGNED32
    sync_win.default = 0
    sync_win.value = 0
    od.add_object(sync_win)

    sync_overflow = ODVariable("Synchronous counter overflow value", 0x1019)
    sync_overflow.data_type = UNSIGNED8
    sync_overflow.default = 0
    sync_overflow.value = 0
    od.add_object(sync_overflow)

    error_behavior = ODArray("Error behavior", 0x1029)
    hsubs = ODVariable("highest_index_supported", 0x1029, 0x00)
    hsubs.data_type = UNSIGNED8
    hsubs.default = 1
    hsubs.value = 1
    hsubs.access_type = "const"
    comm_error = ODVariable("Communication error", 0x1029, 0x01)
    comm_error.data_type = UNSIGNED8
    comm_error.default = 0
    comm_error.value = 0
    error_behavior.add_member(hsubs)
    error_behavior.add_member(comm_error)
    od.add_object(error_behavior)

    nmt_startup = ODVariable("NMTStartup", 0x1F80)
    nmt_startup.data_type = UNSIGNED32
    nmt_startup.default = 0
    nmt_startup.value = 0
    od.add_object(nmt_startup)

    hbconsumer = ODArray("Consumer heartbeat time", 0x1016)
    hsubs = ODVariable("highest_index_supported", 0x1016, 0x00)
    hsubs.data_type = UNSIGNED8
    hsubs.default = 1
    hsubs.value = 1
    hbc = ODVariable("Consumer heartbeat time", 0x1016, 0x01)
    hbc.data_type = UNSIGNED32
    hbc.default = 0
    hbc.value = 0
    hbconsumer.add_member(hsubs)
    hbconsumer.add_member(hbc)
    od.add_object(hbconsumer)

    errorstatus = ODVariable("Error Status Bits", 0x2100)
    errorstatus.data_type = OCTET_STRING
    # Upstream type annotations are obviously wrong
    errorstatus.default = bytes(10)  # type: ignore[assignment]
    errorstatus.value = bytes(10)  # type: ignore[assignment]
    od.add_object(errorstatus)
