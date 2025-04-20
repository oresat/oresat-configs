"""Generate a OreSat card's CANopenNode OD.[c/h] files"""

import os
from itertools import chain

import canopen
from canopen.objectdictionary.datatypes import DOMAIN, OCTET_STRING, UNICODE_STRING, VISIBLE_STRING

from .._yaml_to_od import gen_od
from ..configs.od_config import OdConfig
from . import INDENT4, INDENT8, __version__

_SKIP_INDEXES = [0x1F81, 0x1F82, 0x1F89]
"""CANopenNode skips the data (it just set to NULL) for these indexes for some reason"""

DATA_TYPE_C_TYPES = {
    canopen.objectdictionary.datatypes.BOOLEAN: "bool",
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


def initializer(obj: canopen.objectdictionary.Variable) -> str:
    """Generates a default value initializer for a given ODVariable"""

    if obj.data_type == canopen.objectdictionary.datatypes.VISIBLE_STRING:
        return "{" + ", ".join(f"'{c}'" for c in chain(obj.default, ["\\0"])) + "}"
    if obj.data_type == canopen.objectdictionary.datatypes.OCTET_STRING:
        return "{" + ", ".join(f"0x{b:02X}" for b in obj.default) + "}"
    if obj.data_type == canopen.objectdictionary.datatypes.UNICODE_STRING:
        return "{" + ", ".join(f"0x{ord(c):04X}" for c in chain(obj.default, "\0")) + "}"
    if obj.data_type in canopen.objectdictionary.datatypes.INTEGER_TYPES:
        return f"0x{obj.default:X}"
    if obj.data_type == canopen.objectdictionary.datatypes.BOOLEAN:
        return f"{int(obj.default)}"
    if obj.data_type in canopen.objectdictionary.datatypes.FLOAT_TYPES:
        return str(obj.default)
    raise TypeError(f"Unhandled object {obj.name} datatype: {obj.data_type}")


def attr_lines(od: canopen.ObjectDictionary, index: int) -> list[str]:
    """Generate attr lines for OD.c for a sepecific index"""

    if index in _SKIP_INDEXES:
        return []

    obj = od[index]
    if isinstance(obj, canopen.objectdictionary.Variable):
        return [f"{INDENT4}.x{index:X}_{obj.name} = {initializer(obj)},"]

    if isinstance(obj, canopen.objectdictionary.Array):
        lines = [f"{INDENT4}.x{index:X}_{obj.name}_sub0 = {obj[0].default},"]
        if obj[list(obj.subindices)[1]].data_type == DOMAIN:
            return lines  # skip domains

        lines.append(
            f"{INDENT4}.x{index:X}_{obj.name} = {{"
            + ", ".join(initializer(obj[i]) for i in list(obj.subindices)[1:])
            + "},"
        )
        return lines

    if isinstance(obj, canopen.objectdictionary.Record):
        lines = [f"{INDENT4}.x{index:X}_{obj.name} = {{"]

        for sub in obj.values():
            if sub.data_type == DOMAIN:
                continue  # skip domains
            lines.append(f"{INDENT8}.{sub.name} = {initializer(sub)},")
        lines.append(INDENT4 + "},")
        return lines

    raise TypeError(f"Invalid object {obj.name} type: {type(obj)}")


def _var_data_type_len(var: canopen.objectdictionary.Variable) -> int:
    """Get the length of the variable's data in bytes"""

    if var.data_type in (VISIBLE_STRING, OCTET_STRING):
        return len(var.default)  # char
    if var.data_type == UNICODE_STRING:
        return len(var.default) * 2  # uint16_t
    if var.data_type == DOMAIN:
        return 0
    return DATA_TYPE_C_SIZE[var.data_type] // 8


def _var_attr_flags(var: canopen.objectdictionary.Variable) -> str:
    """Generate the variable attribute flags str"""

    attrs = []

    if var.access_type in ["ro", "const"]:
        attrs.append("ODA_SDO_R")
        if var.pdo_mappable:
            attrs.append("ODA_TPDO")
    elif var.access_type == "wo":
        attrs.append("ODA_SDO_W")
        if var.pdo_mappable:
            attrs.append("ODA_RPDO")
    else:
        attrs.append("ODA_SDO_RW")
        if var.pdo_mappable:
            attrs.append("ODA_TRPDO")

    if var.data_type in (VISIBLE_STRING, UNICODE_STRING):
        attrs.append("ODA_STR")
    elif var.data_type in (DOMAIN, OCTET_STRING) or (DATA_TYPE_C_SIZE[var.data_type] // 8) > 1:
        attrs.append("ODA_MB")

    return " | ".join(attrs)


def data_orig(index: int, obj: canopen.objectdictionary.Variable, name: str, arr: str = "") -> str:
    """Generates the dataOrig field for an OD_obj_*_t"""

    if index in _SKIP_INDEXES or obj.data_type == DOMAIN:
        return "NULL,"
    if obj.data_type in (VISIBLE_STRING, OCTET_STRING, UNICODE_STRING):
        return f"&OD_RAM.x{index:X}_{name}[0]{arr},"
    return f"&OD_RAM.x{index:X}_{name}{arr},"


def obj_entry_body(index: int, obj: canopen.objectdictionary.Variable) -> list[str]:
    """Generates the body of an OD_obj_*_t entry"""

    if isinstance(obj, canopen.objectdictionary.Variable):
        return [
            ".dataOrig = " + data_orig(index, obj, obj.name),
            f".attribute = {_var_attr_flags(obj)},",
            f".dataLength = {_var_data_type_len(obj)}",
        ]
    if isinstance(obj, canopen.objectdictionary.Array):
        first_obj = obj[list(obj.subindices)[1]]
        c_name = DATA_TYPE_C_TYPES[first_obj.data_type]
        if first_obj.data_type == DOMAIN:
            size = "0"
        elif first_obj.data_type in (VISIBLE_STRING, UNICODE_STRING):
            size = f"sizeof({c_name}[{len(first_obj.default) + 1}])"  # add 1 for '\0'
        elif first_obj.data_type == OCTET_STRING:
            size = f"sizeof({c_name}[{len(first_obj.default)}])"
        else:
            size = f"sizeof({c_name})"

        return [
            f".dataOrig0 = &OD_RAM.x{index:X}_{obj.name}_sub0,",
            ".dataOrig = " + data_orig(index, first_obj, obj.name, "[0]"),
            ".attribute0 = ODA_SDO_R,",
            f".attribute = {_var_attr_flags(first_obj)},",
            f".dataElementLength = {_var_data_type_len(first_obj)},",
            f".dataElementSizeof = {size},",
        ]
    if isinstance(obj, canopen.objectdictionary.Record):
        return [
            line
            for i, sub in obj.items()
            for line in [
                "{",
                f"{INDENT4}.dataOrig = " + data_orig(index, sub, f"{obj.name}.{sub.name}"),
                f"{INDENT4}.subIndex = {i},",
                f"{INDENT4}.attribute = {_var_attr_flags(sub)},",
                f"{INDENT4}.dataLength = {_var_data_type_len(sub)}",
                "},",
            ]
        ]
    raise TypeError(f"Invalid object {obj.name} type: {type(obj)}")


def obj_lines(od: canopen.ObjectDictionary, index: int) -> list[str]:
    """Generate lines for OD.c for a specific index"""

    return [
        f"{INDENT4}.o_{index:X}_{od[index].name} = {{",
        *(INDENT8 + line for line in obj_entry_body(index, od[index])),
        f"{INDENT4}}},",
    ]


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

    if dir_path:
        file_path = dir_path + "/OD.c"
    else:  # use value od/dcf path
        file_path = "OD.c"

    lines = [
        f"/* generated by oresat-configs v{__version__} */",
        "",
        "#define OD_DEFINITION",
        '#include "301/CO_ODinterface.h"',
        '#include "OD.h"',
        "",
        "#if CO_VERSION_MAJOR < 4",
        "#error This file is only comatible with CANopenNode v4 and above",
        "#endif",
        "",
    ]

    lines.append("OD_ATTR_RAM OD_RAM_t OD_RAM = {")
    for j in od:
        lines += attr_lines(od, j)
    lines.append("};")
    lines.append("")

    lines.append("typedef struct {")
    for i in od:
        name = od[i].name
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
        name = od[i].name
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


def decl_type(obj: canopen.objectdictionary.Variable, name: str) -> list[str]:
    """Generates a type declaration for an ODVariable"""

    ctype = DATA_TYPE_C_TYPES
    if obj.data_type == DOMAIN:
        return []  # skip domains
    if obj.data_type in (VISIBLE_STRING, UNICODE_STRING):
        return [f"{INDENT4}{ctype[obj.data_type]} {name}[{len(obj.default) + 1}];"]  # + 1 for '\0'
    if obj.data_type == OCTET_STRING:
        return [f"{INDENT4}{ctype[obj.data_type]} {name}[{len(obj.default)}];"]
    return [f"{INDENT4}{ctype[obj.data_type]} {name};"]


def _canopennode_h_lines(od: canopen.ObjectDictionary, index: int) -> list[str]:
    """Generate struct lines for OD.h for a sepecific index"""

    if index in _SKIP_INDEXES:
        return []

    obj = od[index]
    name = f"x{index:X}_{obj.name}"

    if isinstance(obj, canopen.objectdictionary.Variable):
        return decl_type(obj, name)
    if isinstance(obj, canopen.objectdictionary.Array):
        sub = obj[list(obj.subindices)[1]]
        return [
            f"{INDENT4}uint8_t {name}_sub0;",
            *decl_type(sub, f"{name}[OD_CNT_ARR_{index:X}]"),
        ]
    if isinstance(obj, canopen.objectdictionary.Record):
        lines = [f"{INDENT4}struct {{"]
        for sub in obj.values():
            lines.extend(INDENT4 + s for s in decl_type(sub, sub.name))
        lines.append(f"{INDENT4}}} {name};")
        return lines
    raise TypeError(f"Invalid object {obj.name} type: {type(obj)}")


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

    if dir_path:
        file_path = dir_path + "/OD.h"
    else:  # use value od/dcf path
        file_path = "OD.h"

    lines = [
        f"/* generated by oresat-configs v{__version__} */",
        "",
        "#ifndef OD_H",
        "#define OD_H",
        "",
        '#include "301/CO_ODinterface.h"',
        "#include <assert.h>",
        "#include <stdbool.h>",
        "#include <stdint.h>",
        "",
        "#ifdef __cplusplus",
        "#ifndef _Static_assert",
        "#define _Static_assert static_assert",
        "#endif",
        "#endif",
        "",
        (
            "#define STATIC_ASSERT(expression) _Static_assert((expression), "
            '"(" #expression ") failed")'
        ),
        "",
        "#define OD_CNT_NMT 1",
        "#define OD_CNT_HB_PROD 1",
        f"#define OD_CNT_HB_CONS {int(0x1016 in od)}",
        "#define OD_CNT_EM 1",
        "#define OD_CNT_EM_PROD 1",
        f"#define OD_CNT_SDO_SRV {int(0x1200 in od)}",
        f"#define OD_CNT_SDO_CLI {int(0x1280 in od)}",
        f"#define OD_CNT_TIME {int(0x1012 in od)}",
        f"#define OD_CNT_SYNC {int(0x1005 in od and 0x1006 in od)}",
        f"#define OD_CNT_RPDO {od.device_information.nr_of_RXPDO}",
        f"#define OD_CNT_TPDO {od.device_information.nr_of_TXPDO}",
        "",
    ]

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
        name = od[i].name
        lines.append(f"#define OD_ENTRY_H{i:X}_{name.upper()} &OD->list[{num}]")
        num += 1
    lines.append("")

    # add nice #defines for indexes and subindex values
    for i in od:
        name = od[i].name
        lines.append(f"#define OD_INDEX_{name.upper()} 0x{i:X}")

        if not isinstance(od[i], canopen.objectdictionary.Variable):
            for j in od[i]:
                if j == 0:
                    continue
                sub_name = f"{name}_" + od[i][j].name
                lines.append(f"#define OD_SUBINDEX_{sub_name.upper()} 0x{j:X}")
        lines.append("")

    for obj in od.values():
        if isinstance(obj, canopen.objectdictionary.Variable):
            lines += _make_enum_lines(obj)
        elif isinstance(obj, canopen.objectdictionary.Array):
            subindex = list(obj.subindices.keys())[1]
            lines += _make_enum_lines(obj[subindex])
        else:
            for subindex, sub_obj in obj.subindices.items():
                lines += _make_enum_lines(sub_obj)

    for obj in od.values():
        if isinstance(obj, canopen.objectdictionary.Variable):
            lines += _make_bitfields_lines(obj)
        elif isinstance(obj, canopen.objectdictionary.Array):
            subindex = list(obj.subindices.keys())[1]
            lines += _make_bitfields_lines(obj[subindex])
        else:
            for subindex in obj.subindices:
                lines += _make_bitfields_lines(obj[subindex])

    lines.append("#endif /* OD_H */")

    with open(file_path, "w") as f:
        for i in lines:
            f.write(i + "\n")


def _make_enum_lines(obj: canopen.objectdictionary.Variable) -> list[str]:
    lines: list[str] = []
    if not obj.value_descriptions:
        return lines

    obj_name = obj.name
    if isinstance(obj.parent, canopen.objectdictionary.Record):
        obj_name = f"{obj.parent.name}_{obj_name}"
    elif isinstance(obj.parent, canopen.objectdictionary.Array):
        obj_name = obj.parent.name

    lines.append(f"enum {obj_name}_enum " + "{")
    for value, name in obj.value_descriptions.items():
        lines.append(f"{INDENT4}{obj_name.upper()}_{name.upper()} = {value},")
    lines.append("};")
    lines.append("")

    return lines


def _make_bitfields_lines(obj: canopen.objectdictionary.Variable) -> list[str]:
    lines: list[str] = []
    if not obj.bit_definitions:
        return lines

    obj_name = obj.name
    if isinstance(obj.parent, canopen.objectdictionary.Record):
        obj_name = f"{obj.parent.name}_{obj_name}"
    elif isinstance(obj.parent, canopen.objectdictionary.Array):
        obj_name = obj.parent.name

    data_type = DATA_TYPE_C_TYPES[obj.data_type]
    bitfield_name = obj_name + "_bitfield"
    lines.append(f"typedef union {bitfield_name} " + "{")
    lines.append(f"{INDENT4}{data_type} value;")
    lines.append(INDENT4 + "struct __attribute((packed)) {")
    total_bits = 0

    sorted_keys = sorted(obj.bit_definitions, key=lambda k: max(obj.bit_definitions.get(k)))
    bit_defs = {key: obj.bit_definitions[key] for key in sorted_keys}

    for name, bits in bit_defs.items():
        if total_bits < min(bits):
            unused_bits = min(bits) - total_bits
            lines.append(f"{INDENT8}{data_type} unused{total_bits} : {unused_bits};")
            total_bits += unused_bits
        lines.append(f"{INDENT8}{data_type} {name.lower()} : {len(bits)};")
        total_bits += len(bits)
    if total_bits < DATA_TYPE_C_SIZE[obj.data_type]:
        unused_bits = DATA_TYPE_C_SIZE[obj.data_type] - total_bits
        lines.append(f"{INDENT8}{data_type} unused{total_bits} : {unused_bits};")
    lines.append(INDENT4 + "} fields;")
    lines.append("} " + f"{bitfield_name}_t;")
    lines.append(f"STATIC_ASSERT(sizeof({bitfield_name}_t) == sizeof({data_type}));")
    lines.append("")

    return lines


def gen_canopennode_files(card_od_config_path: str, common_od_config_path: str, dir_path: str):
    card_od_config = OdConfig.from_yaml(card_od_config_path)
    if common_od_config_path:
        common_od_config = OdConfig.from_yaml(common_od_config_path)
        od = gen_od([card_od_config, common_od_config])
    else:
        od = gen_od([card_od_config])
    write_canopennode(od, dir_path)
