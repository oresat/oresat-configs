"""Generate a OreSat card's CANopenNode OD.[c/h] files"""

import math as m
import os
import sys
from argparse import ArgumentParser, Namespace
from typing import Any, Optional

import canopen

from .. import Consts, OreSatConfig

GEN_FW_FILES = "generate CANopenNode OD.[c/h] files for a OreSat firmware card"


def build_parser(parser: ArgumentParser) -> ArgumentParser:
    """Configures an ArgumentParser suitable for this script.

    The given parser may be standalone or it may be used as a subcommand in another ArgumentParser.
    """
    parser.description = GEN_FW_FILES
    parser.add_argument(
        "--oresat",
        default=Consts.default().arg,
        choices=[m.arg for m in Consts],
        type=lambda x: x.lower().removeprefix("oresat"),
        help="oresat mission, defaults to %(default)s",
    )
    parser.add_argument(
        "card", help="card name; c3, battery, solar, adcs, reaction_wheel, or diode_test"
    )
    parser.add_argument("-d", "--dir-path", default=".", help='output directory path, default: "."')
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
    parser = build_parser(subparsers.add_parser("fw-files", help=GEN_FW_FILES))
    parser.set_defaults(func=gen_fw_files)


INDENT4 = " " * 4
INDENT8 = " " * 8
INDENT12 = " " * 12

_SKIP_INDEXES = [0x1F81, 0x1F82, 0x1F89]
"""CANopenNode skips the data (it just set to NULL) for these indexes for some reason"""

DATA_TYPE_STR = [
    canopen.objectdictionary.datatypes.VISIBLE_STRING,
    canopen.objectdictionary.datatypes.UNICODE_STRING,
]

DATA_TYPE_C_TYPES = {
    canopen.objectdictionary.datatypes.BOOLEAN: "bool_t",
    canopen.objectdictionary.datatypes.INTEGER8: "int8_t",
    canopen.objectdictionary.datatypes.INTEGER16: "int16_t",
    canopen.objectdictionary.datatypes.INTEGER32: "int32_t",
    canopen.objectdictionary.datatypes.UNSIGNED8: "uint8_t",
    canopen.objectdictionary.datatypes.UNSIGNED16: "uint16_t",
    canopen.objectdictionary.datatypes.UNSIGNED32: "uint32_t",
    canopen.objectdictionary.datatypes.REAL32: "float",
    canopen.objectdictionary.datatypes.VISIBLE_STRING: "char",
    canopen.objectdictionary.datatypes.OCTET_STRING: "uint8_t",
    canopen.objectdictionary.datatypes.UNICODE_STRING: "uint16_t",
    canopen.objectdictionary.datatypes.DOMAIN: None,
    canopen.objectdictionary.datatypes.REAL64: "double",
    canopen.objectdictionary.datatypes.INTEGER64: "int64_t",
    canopen.objectdictionary.datatypes.UNSIGNED64: "uint64_t",
}

DATA_TYPE_C_SIZE = {
    canopen.objectdictionary.datatypes.BOOLEAN: 8,
    canopen.objectdictionary.datatypes.INTEGER8: 8,
    canopen.objectdictionary.datatypes.INTEGER16: 16,
    canopen.objectdictionary.datatypes.INTEGER32: 32,
    canopen.objectdictionary.datatypes.UNSIGNED8: 8,
    canopen.objectdictionary.datatypes.UNSIGNED16: 16,
    canopen.objectdictionary.datatypes.UNSIGNED32: 32,
    canopen.objectdictionary.datatypes.REAL32: 32,
    canopen.objectdictionary.datatypes.REAL64: 64,
    canopen.objectdictionary.datatypes.INTEGER64: 64,
    canopen.objectdictionary.datatypes.UNSIGNED64: 64,
}


def format_name(string: str) -> str:
    """Convert object name to standard format"""

    if len(string) == 0:
        return ""  # nothing to do

    # remove invalid chars for variable names in C
    string = string.replace("-", "_").replace("(", " ").replace(")", " ")
    string = string.replace("  ", " ")

    s_list = string.split()

    name = ""
    for i in s_list:
        try:
            int(i)
        except ValueError:
            name += f"_{i}_"  # add '_' arounds numbers

    name = name.replace("__", "_")

    # remove any trailing '_'
    if name[-1] == "_":
        name = name[:-1]

    # remove any leading '_'
    if name[0] == "_":
        name = name[1:]

    name = name.lower()

    return name


def write_canopennode(od: canopen.ObjectDictionary, dir_path: str = ".") -> None:
    """Save an od/dcf as CANopenNode OD.[c/h] files

    Parameters
    ----------
    od: canopen.ObjectDictionary
        OD data structure to save as file
    dir_path: str
        Path to directory to output OD.[c/h] to. If not set the same dir path as the od will
        be used.
    """

    if dir_path[-1] == "/":
        dir_path = dir_path[:-1]

    if not os.path.isdir(dir_path):
        os.makedirs(dir_path)

    write_canopennode_c(od, dir_path)
    write_canopennode_h(od, dir_path)


def remove_node_id(default: str) -> str:
    """Remove "+$NODEID" or "$NODEID+" from the default value"""

    if default == "":
        return "0"

    temp = default.split("+")

    if len(temp) == 1:
        return default  # does not include $NODEID
    if temp[0] == "$NODEID":
        return temp[1].rsplit()[0]
    if temp[1] == "$NODEID":
        return temp[0].rsplit()[0]

    return default  # does not include $NODEID


def attr_lines(od: canopen.ObjectDictionary, index: int) -> list[str]:
    """Generate attr lines for OD.c for a sepecific index"""

    lines = []

    obj = od[index]
    if isinstance(obj, canopen.objectdictionary.Variable):
        line = f"{INDENT4}.x{index:X}_{format_name(obj.name)} = "

        if obj.data_type == canopen.objectdictionary.datatypes.VISIBLE_STRING:
            line += "{"
            for i in obj.default:
                line += f'"{i}", '
            line += "0}, "
        elif obj.data_type == canopen.objectdictionary.datatypes.OCTET_STRING:
            line += "{"
            value = obj.default.replace("  ", " ")
            for i in value.split(" "):
                line += f"0x{i}, "
            line = line[:-2]  # remove last ', '
            line += "},"
        elif obj.data_type == canopen.objectdictionary.datatypes.UNICODE_STRING:
            line += "{"
            for i in obj.default:
                line += f"0x{ord(i):04X}, "
            line += f"0x{0:04X}"  # add the '\0'
            line += "},"
        elif obj.data_type in canopen.objectdictionary.datatypes.INTEGER_TYPES:
            line += f"0x{obj.default:X},"
        elif obj.data_type == canopen.objectdictionary.datatypes.BOOLEAN:
            line += f"{int(obj.default)},"
        elif obj.data_type in canopen.objectdictionary.datatypes.FLOAT_TYPES:
            line += f"{obj.default},"
        else:
            line += f"{remove_node_id(obj.default)},"

        if index not in _SKIP_INDEXES:
            lines.append(line)
    elif isinstance(obj, canopen.objectdictionary.Array):
        name = format_name(obj.name)
        lines.append(f"{INDENT4}.x{index:X}_{name}_sub0 = {obj[0].default},")
        line = f"{INDENT4}.x{index:X}_{name} = " + "{"

        if obj[list(obj.subindices)[1]].data_type == canopen.objectdictionary.datatypes.DOMAIN:
            return lines  # skip domains

        for i in list(obj.subindices)[1:]:
            if obj[i].data_type == canopen.objectdictionary.datatypes.VISIBLE_STRING:
                line += "{"
                for i in obj[i].default:
                    line += f'"{i}", '
                line += "0}, "
            elif obj[i].data_type == canopen.objectdictionary.datatypes.OCTET_STRING:
                line += "{"
                value = obj[i].default.replace("  ", " ")
                for i in value.split(" "):
                    line += f"0x{i}, "
                line = line[:-2]  # remove trailing ', '
                line += "}, "
            elif obj[i].data_type == canopen.objectdictionary.datatypes.UNICODE_STRING:
                line += "{"
                for i in obj[i].default:
                    line += f"0x{ord(i):04X}, "
                line += f"0x{0:04X}"  # add the '\0'
                line += "}, "
            elif obj[i].data_type in canopen.objectdictionary.datatypes.INTEGER_TYPES:
                line += f"0x{obj[i].default:X}, "
            elif obj[i].data_type == canopen.objectdictionary.datatypes.BOOLEAN:
                line += f"{int(obj[i].default)}, "
            else:
                line += f"{remove_node_id(obj[i].default)}, "

        line = line[:-2]  # remove trailing ', '
        line += "},"

        if index not in _SKIP_INDEXES:
            lines.append(line)
    else:  # ObjectType.Record
        lines.append(f"{INDENT4}.x{index:X}_{format_name(obj.name)} = " + "{")

        for i in obj:
            name = format_name(obj[i].name)
            if obj[i].data_type == canopen.objectdictionary.datatypes.DOMAIN:
                continue  # skip domains

            if obj[i].name == "cob_id":
                # oresat firmware only wants 0x180, 0x280, 0x380, 0x480
                # no +node_id or +1, +2, +3 for TPDO nums > 4
                default = obj[i].default
                if default & 0xFFC not in [0x180, 0x280, 0x380, 0x480, 0x200, 0x300, 0x400, 0x500]:
                    cob_id = (default - od.node_id) & 0xFFC
                    cob_id += default & 0xC0_00_00_00  # add back pdo flags (2 MSBs)
                else:
                    cob_id = default
                lines.append(f"{INDENT8}.{name} = 0x{cob_id:X},")
            elif obj[i].data_type == canopen.objectdictionary.datatypes.VISIBLE_STRING:
                line = f"{INDENT8}.{name} = " + "{"
                for i in obj[i].default:
                    line += f"'{i}', "
                line += "0}, "
                lines.append(line)
            elif obj[i].data_type == canopen.objectdictionary.datatypes.OCTET_STRING:
                value = obj[i].default.hex(sep=" ")
                line = f"{INDENT8}.{name} = " + "{"
                for i in value.split(" "):
                    line += f"0x{i}, "
                line = line[:-2]  # remove trailing ', '
                line += "},"
                lines.append(line)
            elif obj[i].data_type == canopen.objectdictionary.datatypes.UNICODE_STRING:
                line = f"{INDENT8}.{name} = " + "{"
                for i in obj[i].default:
                    line += f"0x{ord(i):04X}, "
                line += f"0x{0:04X}"  # add the '\0'
                line += "},"
                lines.append(line)
            elif obj[i].data_type in canopen.objectdictionary.datatypes.INTEGER_TYPES:
                lines.append(f"{INDENT8}.{name} = 0x{obj[i].default:X},")
            elif obj[i].data_type == canopen.objectdictionary.datatypes.BOOLEAN:
                lines.append(f"{INDENT8}.{name} = {int(obj[i].default)},")
            elif obj[i].data_type in canopen.objectdictionary.datatypes.FLOAT_TYPES:
                lines.append(f"{INDENT8}.{name} = {obj[i].default},")
            else:
                lines.append(f"{INDENT8}.{name} = {remove_node_id(obj[i].default)},")

        lines.append(INDENT4 + "},")

    return lines


def _var_data_type_len(var: canopen.objectdictionary.Variable) -> int:
    """Get the length of the variable's data in bytes"""

    if var.data_type in [
        canopen.objectdictionary.datatypes.VISIBLE_STRING,
        canopen.objectdictionary.datatypes.OCTET_STRING,
    ]:
        length = len(var.default)  # char
    elif var.data_type == canopen.objectdictionary.datatypes.UNICODE_STRING:
        length = len(var.default) * 2  # uint16_t
    elif var.data_type == canopen.objectdictionary.datatypes.DOMAIN:
        length = 0
    else:
        length = DATA_TYPE_C_SIZE[var.data_type] // 8

    return length


def _var_attr_flags(var: canopen.objectdictionary.Variable) -> str:
    """Generate the variable attribute flags str"""

    attr_str = ""

    if var.access_type in ["ro", "const"]:
        attr_str += "ODA_SDO_R"
        if var.pdo_mappable:
            attr_str += " | ODA_TPDO"
    elif var.access_type == "wo":
        attr_str += "ODA_SDO_W"
        if var.pdo_mappable:
            attr_str += " | ODA_RPDO"
    else:
        attr_str += "ODA_SDO_RW"
        if var.pdo_mappable:
            attr_str += " | ODA_TRPDO"

    bytes_types = [
        canopen.objectdictionary.DOMAIN,
        canopen.objectdictionary.OCTET_STRING,
    ]
    if var.data_type in DATA_TYPE_STR:
        attr_str += " | ODA_STR"
    elif var.data_type in bytes_types or (DATA_TYPE_C_SIZE[var.data_type] // 8) > 1:
        attr_str += " | ODA_MB"

    return attr_str


def obj_lines(od: canopen.ObjectDictionary, index: int) -> list[str]:
    """Generate  lines for OD.c for a sepecific index"""

    lines = []

    obj = od[index]
    name = format_name(obj.name)
    lines.append(f"{INDENT4}.o_{index:X}_{name} = " + "{")

    if isinstance(obj, canopen.objectdictionary.Variable):
        if index in _SKIP_INDEXES or obj.data_type == canopen.objectdictionary.datatypes.DOMAIN:
            lines.append(f"{INDENT8}.dataOrig = NULL,")
        elif (
            obj.data_type in DATA_TYPE_STR
            or obj.data_type == canopen.objectdictionary.datatypes.OCTET_STRING
        ):
            lines.append(f"{INDENT8}.dataOrig = &OD_RAM.x{index:X}_{name}[0],")
        else:
            lines.append(f"{INDENT8}.dataOrig = &OD_RAM.x{index:X}_{name},")

        lines.append(f"{INDENT8}.attribute = {_var_attr_flags(obj)},")
        lines.append(f"{INDENT8}.dataLength = {_var_data_type_len(obj)}")
    elif isinstance(obj, canopen.objectdictionary.Array):
        lines.append(f"{INDENT8}.dataOrig0 = &OD_RAM.x{index:X}_{name}_sub0,")

        first_obj = obj[list(obj.subindices)[1]]
        if (
            index in _SKIP_INDEXES
            or first_obj.data_type == canopen.objectdictionary.datatypes.DOMAIN
        ):
            lines.append(f"{INDENT8}.dataOrig = NULL,")
        elif first_obj.data_type in [
            canopen.objectdictionary.datatypes.VISIBLE_STRING,
            canopen.objectdictionary.datatypes.OCTET_STRING,
            canopen.objectdictionary.datatypes.UNICODE_STRING,
        ]:
            lines.append(f"{INDENT8}.dataOrig = &OD_RAM.x{index:X}_{name}[0][0],")
        else:
            lines.append(f"{INDENT8}.dataOrig = &OD_RAM.x{index:X}_{name}[0],")

        lines.append(f"{INDENT8}.attribute0 = ODA_SDO_R,")
        lines.append(f"{INDENT8}.attribute = {_var_attr_flags(first_obj)},")
        length = _var_data_type_len(first_obj)
        lines.append(f"{INDENT8}.dataElementLength = {length},")

        c_name = DATA_TYPE_C_TYPES[first_obj.data_type]
        if first_obj.data_type == canopen.objectdictionary.datatypes.DOMAIN:
            lines.append(f"{INDENT8}.dataElementSizeof = 0,")
        elif first_obj.data_type in DATA_TYPE_STR:
            sub_length = len(first_obj.default) + 1  # add 1 for '\0'
            lines.append(f"{INDENT8}.dataElementSizeof = sizeof({c_name}[{sub_length}]),")
        elif first_obj.data_type == canopen.objectdictionary.datatypes.OCTET_STRING:
            sub_length = m.ceil(len(first_obj.default.replace(" ", "")) / 2)
            lines.append(f"{INDENT8}.dataElementSizeof = sizeof({c_name}[{sub_length}]),")
        else:
            lines.append(f"{INDENT8}.dataElementSizeof = sizeof({c_name}),")
    else:  # ObjectType.DOMAIN
        for i in obj:
            name_sub = format_name(obj[i].name)
            lines.append(INDENT8 + "{")

            if obj[i].data_type == canopen.objectdictionary.datatypes.DOMAIN:
                lines.append(f"{INDENT12}.dataOrig = NULL,")
            elif obj[i].data_type in [
                canopen.objectdictionary.datatypes.VISIBLE_STRING,
                canopen.objectdictionary.datatypes.OCTET_STRING,
                canopen.objectdictionary.datatypes.UNICODE_STRING,
            ]:
                line = f"{INDENT12}.dataOrig = &OD_RAM.x{index:X}_{name}.{name_sub}[0],"
                lines.append(line)
            else:
                lines.append(f"{INDENT12}.dataOrig = &OD_RAM.x{index:X}_{name}.{name_sub},")

            lines.append(f"{INDENT12}.subIndex = {i},")
            lines.append(f"{INDENT12}.attribute = {_var_attr_flags(obj[i])},")
            lines.append(f"{INDENT12}.dataLength = {_var_data_type_len(obj[i])}")
            lines.append(INDENT8 + "},")

    lines.append(INDENT4 + "},")

    return lines


def write_canopennode_c(od: canopen.ObjectDictionary, dir_path: str = ".") -> None:
    """Save an od/dcf as a CANopenNode OD.c file

    Parameters
    ----------
    od: canopen.ObjectDictionary
        od data structure to save as file
    dir_path: str
        Path to directory to output OD.c to. If not set the same dir path as the od will
        be used.
    """

    lines = []

    if dir_path:
        file_path = dir_path + "/OD.c"
    else:  # use value od/dcf path
        file_path = "OD.c"

    lines.append("#define OD_DEFINITION")
    lines.append('#include "301/CO_ODinterface.h"')
    lines.append('#include "OD.h"')
    lines.append("")

    lines.append("#if CO_VERSION_MAJOR < 4")
    lines.append("#error This file is only comatible with CANopenNode v4 and above")
    lines.append("#endif")
    lines.append("")

    lines.append("OD_ATTR_RAM OD_RAM_t OD_RAM = {")
    for j in od:
        lines += attr_lines(od, j)
    lines.append("};")
    lines.append("")

    lines.append("typedef struct {")
    for i in od:
        name = format_name(od[i].name)
        if isinstance(od[i], canopen.objectdictionary.Variable):
            lines.append(f"{INDENT4}OD_obj_var_t o_{i:X}_{name};")
        elif isinstance(od[i], canopen.objectdictionary.Array):
            lines.append(f"{INDENT4}OD_obj_array_t o_{i:X}_{name};")
        else:
            size = len(od[i])
            lines.append(f"{INDENT4}OD_obj_record_t o_{i:X}_{name}[{size}];")
    lines.append("} ODObjs_t;")
    lines.append("")

    lines.append("static CO_PROGMEM ODObjs_t ODObjs = {")
    for i in od:
        lines += obj_lines(od, i)
    lines.append("};")
    lines.append("")

    lines.append("static OD_ATTR_OD OD_entry_t ODList[] = {")
    for i in od:
        name = format_name(od[i].name)
        if isinstance(od[i], canopen.objectdictionary.Variable):
            length = 1
            obj_type = "ODT_VAR"
        elif isinstance(od[i], canopen.objectdictionary.Array):
            length = len(od[i])
            obj_type = "ODT_ARR"
        else:
            length = len(od[i])
            obj_type = "ODT_REC"
        temp = f"0x{i:X}, 0x{length:02X}, {obj_type}, &ODObjs.o_{i:X}_{name}, NULL"
        lines.append(INDENT4 + "{" + temp + "},")
    lines.append(INDENT4 + "{0x0000, 0x00, 0, NULL, NULL}")
    lines.append("};")
    lines.append("")

    lines.append("static OD_t _OD = {")
    lines.append(f"{INDENT4}(sizeof(ODList) / sizeof(ODList[0])) - 1,")
    lines.append(f"{INDENT4}&ODList[0]")
    lines.append("};")
    lines.append("")

    lines.append("OD_t *OD = &_OD;")

    with open(file_path, "w") as f:
        for i in lines:
            f.write(i + "\n")


def _canopennode_h_lines(od: canopen.ObjectDictionary, index: int) -> list[str]:
    """Generate struct lines for OD.h for a sepecific index"""

    lines = []

    obj = od[index]
    name = format_name(obj.name)

    if isinstance(obj, canopen.objectdictionary.Variable):
        c_name = DATA_TYPE_C_TYPES[obj.data_type]

        if obj.data_type == canopen.objectdictionary.datatypes.DOMAIN:
            pass  # skip domains
        elif obj.data_type in DATA_TYPE_STR:
            length = len(obj.default) + 1  # add 1 for '\0'
            lines.append(f"{INDENT4}{c_name} x{index:X}_{name}[{length}];")
        elif obj.data_type == canopen.objectdictionary.datatypes.OCTET_STRING:
            length = len(obj.default.replace(" ", "")) // 2  # aka number of uint8s
            lines.append(f"{INDENT4}{c_name} x{index:X}_{name}[{length}];")
        else:
            lines.append(f"{INDENT4}{c_name} x{index:X}_{name};")
    elif isinstance(obj, canopen.objectdictionary.Array):
        first_obj = obj[list(obj.subindices)[1]]
        c_name = DATA_TYPE_C_TYPES[first_obj.data_type]
        length_str = f"OD_CNT_ARR_{index:X}"
        lines.append(f"{INDENT4}uint8_t x{index:X}_{name}_sub0;")

        if first_obj.data_type == canopen.objectdictionary.datatypes.DOMAIN:
            pass  # skip domains
        elif index in _SKIP_INDEXES:
            pass
        elif first_obj.data_type in DATA_TYPE_STR:
            sub_length = len(first_obj.default) + 1  # add 1 for '\0'
            lines.append(f"{INDENT4}{c_name} x{index:X}_{name}[{length_str}][{sub_length}];")
        elif first_obj.data_type == canopen.objectdictionary.datatypes.OCTET_STRING:
            sub_length = m.ceil(len(first_obj.default.replace(" ", "")) / 2)
            lines.append(f"{INDENT4}{c_name} x{index:X}_{name}[{length_str}][{sub_length}];")
        else:
            lines.append(f"{INDENT4}{c_name} x{index:X}_{name}[{length_str}];")
    else:
        lines.append(INDENT4 + "struct {")
        for i in obj:
            data_type = obj[i].data_type
            c_name = DATA_TYPE_C_TYPES[data_type]
            sub_name = format_name(obj[i].name)

            if data_type == canopen.objectdictionary.datatypes.DOMAIN:
                continue  # skip domains

            if data_type in DATA_TYPE_STR:
                length = len(obj[i].default) + 1  # add 1 for '\0'
                lines.append(f"{INDENT8}{c_name} {sub_name}[{length}];")
            elif data_type == canopen.objectdictionary.datatypes.OCTET_STRING:
                sub_length = len(obj[list(obj.subindices)[1]].default)
                lines.append(f"{INDENT8}{c_name} {sub_name}[{sub_length}];")
            else:
                lines.append(f"{INDENT8}{c_name} {sub_name};")

        lines.append(INDENT4 + "}" + f" x{index:X}_{name};")

    return lines


def write_canopennode_h(od: canopen.ObjectDictionary, dir_path: str = ".") -> None:
    """Save an od/dcf as a CANopenNode OD.h file

    Parameters
    ----------
    od: canopen.ObjectDictionary
        od data structure to save as file
    dir_path: str
        Path to directory to output OD.h to. If not set the same dir path as the od will
        be used.
    """

    lines = []

    if dir_path:
        file_path = dir_path + "/OD.h"
    else:  # use value od/dcf path
        file_path = "OD.h"

    lines.append("#ifndef OD_H")
    lines.append("#define OD_H")
    lines.append("")

    lines.append("#define OD_CNT_NMT 1")
    lines.append("#define OD_CNT_EM 1")
    lines.append("#define OD_CNT_SYNC 1")
    lines.append("#define OD_CNT_EM_PROD 1")
    lines.append("#define OD_CNT_HB_PROD 1")
    lines.append("#define OD_CNT_HB_CONS 0")
    lines.append("#define OD_CNT_SDO_SRV 1")
    if 0x1280 in od:
        lines.append("#define OD_CNT_SDO_CLI 1")
    if od.device_information.nr_of_RXPDO > 0:
        lines.append(f"#define OD_CNT_RPDO {od.device_information.nr_of_RXPDO}")
    if od.device_information.nr_of_TXPDO > 0:
        lines.append(f"#define OD_CNT_TPDO {od.device_information.nr_of_TXPDO}")
    lines.append("")

    for i in od:
        if isinstance(od[i], canopen.objectdictionary.Array):
            lines.append(f"#define OD_CNT_ARR_{i:X} {len(od[i]) - 1}")
    lines.append("")

    lines.append("typedef struct {")
    for j in od:
        lines += _canopennode_h_lines(od, j)
    lines.append("} OD_RAM_t;")
    lines.append("")

    lines.append("#ifndef OD_ATTR_RAM")
    lines.append("#define OD_ATTR_RAM")
    lines.append("#endif")
    lines.append("extern OD_ATTR_RAM OD_RAM_t OD_RAM;")
    lines.append("")

    lines.append("#ifndef OD_ATTR_OD")
    lines.append("#define OD_ATTR_OD")
    lines.append("#endif")
    lines.append("extern OD_ATTR_OD OD_t *OD;")
    lines.append("")

    num = 0
    for i in od:
        lines.append(f"#define OD_ENTRY_H{i:X} &OD->list[{num}]")
        num += 1
    lines.append("")

    num = 0
    for i in od:
        name = format_name(od[i].name)
        lines.append(f"#define OD_ENTRY_H{i:X}_{name.upper()} &OD->list[{num}]")
        num += 1
    lines.append("")

    # add nice #defines for indexes and subindex values
    for i in od:
        if i < 0x2000:
            continue  # only care about common, card, and RPDO mapped objects

        name = format_name(od[i].name)
        lines.append(f"#define OD_INDEX_{name.upper()} 0x{i:X}")

        if not isinstance(od[i], canopen.objectdictionary.Variable):
            for j in od[i]:
                if j == 0:
                    continue
                sub_name = f"{name}_" + format_name(od[i][j].name)
                lines.append(f"#define OD_SUBINDEX_{sub_name.upper()} 0x{j:X}")
        lines.append("")

    lines.append("#endif /* OD_H */")

    with open(file_path, "w") as f:
        for i in lines:
            f.write(i + "\n")


def gen_fw_files(args: Optional[Namespace] = None) -> None:
    """generate CANopenNode firmware files main"""
    if args is None:
        args = build_parser(ArgumentParser()).parse_args()

    config = OreSatConfig(args.oresat)

    arg_card = args.card.lower().replace("-", "_")
    if arg_card == "c3":
        od = config.od_db["c3"]
    elif arg_card in ["solar", "solar_module"]:
        od = config.od_db["solar_1"]
    elif arg_card in ["battery", "bat"]:
        od = config.od_db["battery_1"]
    elif arg_card in ["imu", "adcs"]:
        od = config.od_db["adcs"]
    elif arg_card in ["rw", "reaction_wheel"]:
        od = config.od_db["rw_1"]
    elif arg_card in ["diode", "diode_test"]:
        od = config.od_db["diode_test"]
    elif arg_card == "base":
        od = config.fw_base_od
    else:
        print(f"invalid oresat card: {args.card}")
        sys.exit()

    write_canopennode(od, args.dir_path)
