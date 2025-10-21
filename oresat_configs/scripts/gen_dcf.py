"""Generate a DCF for from an OreSat card's object directory."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import canopen

if TYPE_CHECKING:
    from argparse import Namespace

    from canopen.objectdictionary import Variable

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
    desc = "generate DCF file for OreSat node(s)"
    parser = subparsers.add_parser("dcf", description=desc, help=desc)
    parser.set_defaults(func=gen_dcf)

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


def generate_dcf(od: canopen.ObjectDictionary) -> tuple[str, list[str]]:
    """Save an od/dcf file

    Parameters
    ----------
    od: canopen.ObjectDictionary
        od data structure to save as file
    """

    lines = []
    dev_info = od.device_information
    assert dev_info.product_name is not None
    file_name = dev_info.product_name + ".dcf"
    file_name = file_name.lower().replace(" ", "_")
    now = datetime.now(timezone.utc)

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
    lines.extend(f"BaudRate_{i}=1" for i in (10, 12, 50, 125, 250, 500, 800, 1000))  # baud in kpps
    lines.append(f"SimpleBootUpMaster={1 if dev_info.simple_boot_up_master else 0}")
    lines.append(f"SimpleBootUpSlave={1 if dev_info.simple_boot_up_slave else 0}")
    lines.append(f"Granularity={dev_info.granularity}")
    lines.append(f"DynamicChannelsSupported={1 if dev_info.dynamic_channels_supported else 0}")
    lines.append(f"GroupMessaging={1 if dev_info.group_messaging else 0}")
    lines.append(f"NrOfRXPDO={dev_info.nr_of_RXPDO}")
    lines.append(f"NrOfTXPDO={dev_info.nr_of_TXPDO}")
    lines.append(f"LSS_Supported={1 if dev_info.LSS_supported else 0}")
    lines.append("")

    lines.append("[DeviceComissioning]")  # only one 'm' in header
    lines.append(f"NodeID=0x{od.node_id:X}")
    lines.append(f"NodeName={dev_info.product_name}")
    assert od.bitrate is not None
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
    lines.extend(f"Dummy000{i}=1" for i in range(8))
    lines.append("")

    lines.append("[Comments]")
    lines.append("Lines=0")
    lines.append("")

    lines.append("[MandatoryObjects]")
    mandatory_objs = [i for i in (0x1000, 0x1001, 0x1018) if i in od]
    lines.append(f"SupportedObjects={len(mandatory_objs)}")
    for i in mandatory_objs:
        num = mandatory_objs.index(i) + 1
        value = f"0x{i:04X}"
        lines.append(f"{num}={value}")
    lines.append("")

    lines += _objects_lines(od, mandatory_objs)

    lines.append("[OptionalObjects]")
    optional_objs = [
        i for i in od if (0x1002 <= i <= 0x1FFF and i != 0x1018) or (0x6000 <= i <= 0xFFFF)
    ]
    lines.append(f"SupportedObjects={len(optional_objs)}")
    for i in optional_objs:
        num = optional_objs.index(i) + 1
        value = f"0x{i:04X}"
        lines.append(f"{num}={value}")
    lines.append("")

    lines += _objects_lines(od, optional_objs)

    lines.append("[ManufacturerObjects]")
    manufacturer_objs = [i for i in od if 0x2000 <= i <= 0x5FFF]
    lines.append(f"SupportedObjects={len(manufacturer_objs)}")
    for i in manufacturer_objs:
        num = manufacturer_objs.index(i) + 1
        value = f"0x{i:04X}"
        lines.append(f"{num}={value}")
    lines.append("")

    lines += _objects_lines(od, manufacturer_objs)
    return (file_name, lines)


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


def _variable_lines(variable: Variable, index: int, subindex: int | None = None) -> list[str]:
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
            tmp = cast(bytes, variable.default).hex(sep=" ")
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


def gen_dcf(args: Namespace) -> None:
    """Gen_dcf main."""
    config = OreSatConfig(args.oresat)

    if args.card.lower() == "all":
        ods = list(config.od_db.values())
    else:
        ods = [config.od_db[args.card.lower()]]

    for od in ods:
        name, lines = generate_dcf(od)
        with (args.dir_path / name).open("w") as f:
            f.writelines(line + "\n" for line in lines)
