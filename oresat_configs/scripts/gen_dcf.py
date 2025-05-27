"""Generate a DCF for from an OreSat card's object directory."""

from argparse import ArgumentParser, Namespace
from datetime import datetime
from typing import Any, Optional

import canopen
from canopen.objectdictionary import Variable

from .. import Mission, OreSatConfig

GEN_DCF = "generate DCF file for OreSat node(s)"


def build_parser(parser: ArgumentParser) -> ArgumentParser:
    """Configures an ArgumentParser suitable for this script.

    The given parser may be standalone or it may be used as a subcommand in another ArgumentParser.
    """
    parser.description = GEN_DCF
    parser.add_argument(
        "--oresat",
        default=Mission.default().arg,
        choices=[m.arg for m in Mission],
        type=lambda x: x.lower().removeprefix("oresat"),
        help="Oresat Mission. (Default: %(default)s)",
    )
    parser.add_argument("card", help="card name; all, c3, gps, star_tracker_1, etc")
    parser.add_argument("-d", "--dir-path", default=".", help='directory path; defautl "."')
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
    parser = build_parser(subparsers.add_parser("dcf", help=GEN_DCF))
    parser.set_defaults(func=gen_dcf)


def write_od(od: canopen.ObjectDictionary, dir_path: str = ".") -> None:
    """Save an od/dcf file

    Parameters
    ----------
    od: canopen.ObjectDictionary
        od data structure to save as file
    dir_path: str
        Directory path of dcf to save.
    """

    lines = []

    dev_info = od.device_information
    file_name = dev_info.product_name + ".dcf"
    file_name = file_name.lower().replace(" ", "_")
    file_path = f"{dir_path}/{file_name}"
    now = datetime.now()

    # file info seciton
    lines.append("[FileInfo]")
    lines.append(f"FileName={file_name}")
    lines.append("FileVersion=0")
    lines.append("FileRevision=0")
    lines.append("LastEDS=")
    lines.append("EDSVersion=4.0")
    lines.append("Description=")
    lines.append("CreationTime=" + now.strftime("%I:%M%p"))
    lines.append("CreationDate=" + now.strftime("%m-%d-%Y"))
    lines.append("CreatedBy=PSAS")
    lines.append("ModificationTime=" + now.strftime("%I:%M%p"))
    lines.append("ModificationDate=" + now.strftime("%m-%d-%Y"))
    lines.append("ModifiedBy=PSAS")
    lines.append("")

    # device info seciton
    lines.append("[DeviceInfo]")
    lines.append(f"VendorName={dev_info.vendor_name}")
    lines.append(f"VendorNumber={dev_info.vendor_number}")
    lines.append(f"ProductName={dev_info.product_name}")
    lines.append(f"ProductNumber={dev_info.product_number}")
    lines.append(f"RevisionNumber={dev_info.revision_number}")
    lines.append(f"OrderCode={dev_info.order_code}")
    for i in [10, 12, 50, 125, 250, 500, 800, 1000]:  # baud rates in kpps
        lines.append(f"BaudRate_{i}=1")
    lines.append(f"SimpleBootUpMaster={int(dev_info.simple_boot_up_master)}")
    lines.append(f"SimpleBootUpSlave={int(dev_info.simple_boot_up_slave)}")
    lines.append(f"Granularity={dev_info.granularity}")
    lines.append(f"DynamicChannelsSupported={int(dev_info.dynamic_channels_supported)}")
    lines.append(f"GroupMessaging={int(dev_info.group_messaging)}")
    lines.append(f"NrOfRXPDO={dev_info.nr_of_RXPDO}")
    lines.append(f"NrOfTXPDO={dev_info.nr_of_TXPDO}")
    lines.append(f"LSS_Supported={int(dev_info.LSS_supported)}")
    lines.append("")

    lines.append("[DeviceComissioning]")  # only one 'm' in header
    lines.append(f"NodeID=0x{od.node_id:X}")
    lines.append(f"NodeName={dev_info.product_name}")
    lines.append(f"BaudRate={od.bitrate // 1000}")  # in kpbs
    lines.append("NetNumber=0")
    lines.append("NetworkName=0")
    if dev_info.product_name in ["c3", "C3"]:
        lines.append("CANopenManager=1")
    else:
        lines.append("CANopenManager=0")
    lines.append("LSS_SerialNumber=0")
    lines.append("")

    lines.append("[DummyUsage]")
    for i in range(8):
        lines.append(f"Dummy000{i}=1")
    lines.append("")

    lines.append("[Comments]")
    lines.append("Lines=0")
    lines.append("")

    lines.append("[MandatoryObjects]")
    mandatory_objs = []
    for i in [0x1000, 0x1001, 0x1018]:
        if i in od:
            mandatory_objs.append(i)
    lines.append(f"SupportedObjects={len(mandatory_objs)}")
    for i in mandatory_objs:
        num = mandatory_objs.index(i) + 1
        value = f"0x{i:04X}"
        lines.append(f"{num}={value}")
    lines.append("")

    lines += _objects_lines(od, mandatory_objs)

    lines.append("[OptionalObjects]")
    optional_objs = []
    for i in od:
        if (i >= 0x1002 and i <= 0x1FFF and i != 0x1018) or (i >= 0x6000 and i <= 0xFFFF):
            optional_objs.append(i)
    lines.append(f"SupportedObjects={len(optional_objs)}")
    for i in optional_objs:
        num = optional_objs.index(i) + 1
        value = f"0x{i:04X}"
        lines.append(f"{num}={value}")
    lines.append("")

    lines += _objects_lines(od, optional_objs)

    lines.append("[ManufacturerObjects]")
    manufacturer_objs = []
    for i in od:
        if i >= 0x2000 and i <= 0x5FFF:
            manufacturer_objs.append(i)
    lines.append(f"SupportedObjects={len(manufacturer_objs)}")
    for i in manufacturer_objs:
        num = manufacturer_objs.index(i) + 1
        value = f"0x{i:04X}"
        lines.append(f"{num}={value}")
    lines.append("")

    lines += _objects_lines(od, manufacturer_objs)

    with open(file_path, "w") as f:
        for line in lines:
            f.write(line + "\n")


def _objects_lines(od: canopen.ObjectDictionary, indexes: list[int]) -> list[str]:
    lines = []

    for i in indexes:
        obj = od[i]
        if isinstance(obj, canopen.objectdictionary.Variable):
            lines += _variable_lines(obj, i)
        elif isinstance(obj, canopen.objectdictionary.Array):
            lines += _array_lines(obj, i)
        elif isinstance(obj, canopen.objectdictionary.Record):
            lines += _record_lines(obj, i)

    return lines


def _variable_lines(variable: Variable, index: int, subindex: Optional[int] = None) -> list[str]:
    lines = []

    if subindex is None:
        lines.append(f"[{index:X}]")
    else:
        lines.append(f"[{index:X}sub{subindex:X}]")

    lines.append(f"ParameterName={variable.name}")
    lines.append("ObjectType=0x07")
    lines.append(f"DataType=0x{variable.data_type:04X}")
    lines.append(f"AccessType={variable.access_type}")
    if variable.default:  # optional
        if variable.data_type == canopen.objectdictionary.OCTET_STRING:
            tmp = variable.default.hex(sep=" ")
            lines.append(f"DefaultValue={tmp}")
        elif variable.data_type == canopen.objectdictionary.BOOLEAN:
            lines.append(f"DefaultValue={int(variable.default)}")
        else:
            lines.append(f"DefaultValue={variable.default}")
    if variable.pdo_mappable:  # optional
        lines.append(f"PDOMapping={int(variable.pdo_mappable)}")
    lines.append("")

    return lines


def _array_lines(array: canopen.objectdictionary.Array, index: int) -> list[str]:
    lines = []

    lines.append(f"[{index:X}]")

    lines.append(f"ParameterName={array.name}")
    lines.append("ObjectType=0x08")
    lines.append(f"SubNumber={len(array)}")
    lines.append("")

    for i in array.subindices:
        lines += _variable_lines(array[i], index, i)

    return lines


def _record_lines(record: canopen.objectdictionary.Record, index: int) -> list[str]:
    lines = []

    lines.append(f"[{index:X}]")

    lines.append(f"ParameterName={record.name}")
    lines.append("ObjectType=0x09")
    lines.append(f"SubNumber={len(record)}")
    lines.append("")

    for i in record.subindices:
        lines += _variable_lines(record[i], index, i)

    return lines


def gen_dcf(args: Optional[Namespace] = None) -> None:
    """Gen_dcf main."""
    if args is None:
        args = build_parser(ArgumentParser()).parse_args()

    config = OreSatConfig(args.oresat)

    if args.card.lower() == "all":
        for od in config.od_db.values():
            write_od(od, args.dir_path)
    else:
        od = config.od_db[args.card.lower()]
        write_od(od, args.dir_path)
