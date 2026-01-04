"""Generate a OreSat card's CANopenNode OD.[c/h] files"""

from __future__ import annotations

from collections.abc import Iterable
from itertools import chain, islice
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from argparse import Namespace

import canopen
from canopen.objectdictionary import ODArray, ODRecord, ODVariable
from canopen.objectdictionary.datatypes import DOMAIN, OCTET_STRING, UNICODE_STRING, VISIBLE_STRING

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
    desc = "generate CANopenNode OD.[c/h] files for an OreSat firmware card"
    parser = subparsers.add_parser("fw-files", description=desc, help=desc)
    parser.set_defaults(func=gen_fw_files)

    parser.add_argument(
        "--oresat",
        default=Mission.default().arg,
        choices=[m.arg for m in Mission],
        type=lambda x: x.lower().removeprefix("oresat"),
        help="Oresat Mission. (Default: %(default)s)",
    )
    parser.add_argument(
        "card",
        help="card name; c3, battery, solar, adcs, reaction_wheel, or diode_test",
    )
    parser.add_argument(
        "-d", "--dir-path", default=".", type=Path, help='output directory path, default: "."'
    )
    parser.add_argument(
        "-hw",
        "--hardware-version",
        help="hardware board version string, usually defined in make",
    )
    parser.add_argument(
        "-fw",
        "--firmware-version",
        help="firmware version string, usually git describe output",
    )


def indent(*lines: str | Iterable) -> list[str]:
    indented = []
    for line in lines:
        if isinstance(line, str):
            indented.append("    " + line)
        elif isinstance(line, Iterable):
            indented += indent(*line)
    return indented


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


def generate_canopennode(od: canopen.ObjectDictionary) -> tuple[list[str], list[str]]:
    """Create the text of CANopenNode OD.[c/h] files from the od

    Parameters
    ----------
    od:
        OD data structure to save as file
    """

    # remove node id from emcy cob id
    if 0x1014 in od:
        emcy = od[0x1014]
        assert isinstance(emcy, ODVariable)
        emcy.default = 0x80

    assert od.node_id is not None
    max_pdos = 12 if od.node_id == 0x01 else 16  # C3 has 16 pdos
    tpdo_cob_ids = [0x180 + (0x100 * (i % 4)) + (i // 4) + od.node_id for i in range(max_pdos)]
    rpdo_cob_ids = [i + 0x80 for i in tpdo_cob_ids]

    def _remove_pdo_cob_ids(start: int, cob_ids: list[int]) -> None:
        assert od.node_id is not None
        for index in range(start, start + 0x1FF):
            try:
                pdo = od[index]
            except KeyError:
                continue
            assert isinstance(pdo, ODRecord)
            default = pdo['cob_id'].default
            assert default is not None
            if default & 0x7FF in cob_ids:
                cob_id = ((default - od.node_id) & 0xFFC) | default & 0xC000_000
            else:
                cob_id = default
            pdo['cob_id'].default = cob_id

    # remove node id from pdo cob ids
    _remove_pdo_cob_ids(0x1400, rpdo_cob_ids)
    _remove_pdo_cob_ids(0x1800, tpdo_cob_ids)

    odc = generate_canopennode_c(od)
    odh = generate_canopennode_h(od)
    return (odc, odh)


def initializer(obj: ODVariable) -> str:
    """Generates a default value initializer for a given ODVariable"""

    if obj.data_type == canopen.objectdictionary.datatypes.VISIBLE_STRING:
        return "{" + ", ".join(f"'{c}'" for c in chain(cast(str, obj.default), ["\\0"])) + "}"
    if obj.data_type == canopen.objectdictionary.datatypes.OCTET_STRING:
        return "{" + ", ".join(f"0x{b:02X}" for b in cast(bytes, obj.default)) + "}"
    if obj.data_type == canopen.objectdictionary.datatypes.UNICODE_STRING:
        return "{" + ", ".join(f"0x{ord(c):04X}" for c in chain(cast(str, obj.default), "\0")) + "}"
    if obj.data_type in canopen.objectdictionary.datatypes.INTEGER_TYPES:
        return f"0x{obj.default:X}"
    if obj.data_type == canopen.objectdictionary.datatypes.BOOLEAN:
        return f"{int(cast(bool, obj.default))}"
    if obj.data_type in canopen.objectdictionary.datatypes.FLOAT_TYPES:
        return str(obj.default)
    raise TypeError(f"Unhandled object {obj.name} datatype: {obj.data_type}")


def attr_lines(obj: ODVariable | ODRecord | ODArray) -> list[str]:
    """Generate attr lines for OD.c for a specific index"""

    if obj.index in _SKIP_INDEXES:
        return []

    if isinstance(obj, ODVariable):
        return [f".x{obj.index:X}_{obj.name} = {initializer(obj)},"]

    if isinstance(obj, ODArray):
        lines = [f".x{obj.index:X}_{obj.name}_sub0 = {obj[0].default},"]
        if next(islice(obj.values(), 1, None)).data_type == DOMAIN:
            return lines  # skip domains

        lines.append(
            f".x{obj.index:X}_{obj.name} = {{"
            + ", ".join(initializer(sub) for sub in islice(obj.values(), 1, None))
            + "},",
        )
        return lines

    if isinstance(obj, ODRecord):
        return [
            f".x{obj.index:X}_{obj.name} = {{",
            *indent(
                f".{sub.name} = {initializer(sub)},"
                for sub in obj.values()
                if sub.data_type != DOMAIN
            ),
            "},",
        ]

    raise TypeError(f"Invalid object {obj.name} type: {type(obj)}")


def _var_data_type_len(var: ODVariable) -> int:
    """Get the length of the variable's data in bytes"""

    if var.data_type in (VISIBLE_STRING, OCTET_STRING):
        return len(cast(str, var.default))  # char
    if var.data_type == UNICODE_STRING:
        return len(cast(str, var.default)) * 2  # uint16_t
    if var.data_type == DOMAIN:
        return 0
    assert var.data_type is not None
    return DATA_TYPE_C_SIZE[var.data_type] // 8


def _var_attr_flags(var: ODVariable) -> str:
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

    assert var.data_type is not None
    if var.data_type in (VISIBLE_STRING, UNICODE_STRING):
        attrs.append("ODA_STR")
    elif var.data_type in (DOMAIN, OCTET_STRING) or (DATA_TYPE_C_SIZE[var.data_type] // 8) > 1:
        attrs.append("ODA_MB")

    return " | ".join(attrs)


def data_orig(index: int, obj: ODVariable, name: str, arr: str = "") -> str:
    """Generates the dataOrig field for an OD_obj_*_t"""

    if index in _SKIP_INDEXES or obj.data_type == DOMAIN:
        return "NULL,"
    if obj.data_type in (VISIBLE_STRING, OCTET_STRING, UNICODE_STRING):
        return f"&OD_RAM.x{index:X}_{name}[0]{arr},"
    return f"&OD_RAM.x{index:X}_{name}{arr},"


def obj_entry_body(index: int, obj: ODVariable | ODRecord | ODArray) -> list[str]:
    """Generates the body of an OD_obj_*_t entry"""

    if isinstance(obj, ODVariable):
        return [
            ".dataOrig = " + data_orig(index, obj, obj.name),
            f".attribute = {_var_attr_flags(obj)},",
            f".dataLength = {_var_data_type_len(obj)}",
        ]
    if isinstance(obj, ODArray):
        first_obj = next(islice(obj.values(), 1, None))
        assert first_obj.data_type is not None
        c_name = DATA_TYPE_C_TYPES[first_obj.data_type]
        if first_obj.data_type == DOMAIN:
            size = "0"
        elif first_obj.data_type in (VISIBLE_STRING, UNICODE_STRING):
            size = f"sizeof({c_name}[{len(cast(str, first_obj.default)) + 1}])"  # add 1 for '\0'
        elif first_obj.data_type == OCTET_STRING:
            size = f"sizeof({c_name}[{len(cast(bytes, first_obj.default))}])"
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
    if isinstance(obj, ODRecord):
        return [
            line
            for i, sub in obj.items()
            for line in [
                "{",
                *indent(
                    ".dataOrig = " + data_orig(index, sub, f"{obj.name}.{sub.name}"),
                    f".subIndex = {i},",
                    f".attribute = {_var_attr_flags(sub)},",
                    f".dataLength = {_var_data_type_len(sub)}",
                ),
                "},",
            ]
        ]
    raise TypeError(f"Invalid object {obj.name} type: {type(obj)}")


def obj_lines(obj: ODVariable | ODRecord | ODArray) -> list[str]:
    """Generate lines for OD.c for a specific index"""

    return [
        f".o_{obj.index:X}_{obj.name} = {{",
        *indent(obj_entry_body(obj.index, obj)),
        "},",
    ]


def _odobj_t(obj: ODVariable | ODRecord | ODArray) -> str:
    if isinstance(obj, ODVariable):
        return f"OD_obj_var_t o_{obj.index:X}_{obj.name};"
    if isinstance(obj, ODArray):
        return f"OD_obj_array_t o_{obj.index:X}_{obj.name};"
    if isinstance(obj, ODRecord):
        return f"OD_obj_record_t o_{obj.index:X}_{obj.name}[{len(obj)}];"
    raise TypeError(f"Invalid object {obj.name} type: {type(obj)}")


def _odlist(obj: ODVariable | ODRecord | ODArray) -> str:
    i = f'{obj.index:X}'
    if isinstance(obj, ODVariable):
        return f"{{0x{i}, 0x{1:02X}, ODT_VAR, &ODObjs.o_{i}_{obj.name}, NULL}},"
    if isinstance(obj, ODArray):
        return f"{{0x{i}, 0x{len(obj):02X}, ODT_ARR, &ODObjs.o_{i}_{obj.name}, NULL}},"
    if isinstance(obj, ODRecord):
        return f"{{0x{i}, 0x{len(obj):02X}, ODT_REC, &ODObjs.o_{i}_{obj.name}, NULL}},"
    raise TypeError(f"Invalid object {obj.name} type: {type(obj)}")


def generate_canopennode_c(od: canopen.ObjectDictionary) -> list[str]:
    """Transform an od into a CANopenNode OD.c file

    Parameters
    ----------
    od: canopen.ObjectDictionary
        od data structure to save as file
    """

    return [
        "#define OD_DEFINITION",
        '#include "OD.h"',
        "",
        "#if CO_VERSION_MAJOR < 4",
        "#error This file is only comatible with CANopenNode v4 and above",
        "#endif",
        "",
        "OD_ATTR_RAM OD_RAM_t OD_RAM = {",
        *indent(attr_lines(obj) for obj in od.values()),
        "};",
        "",
        "typedef struct {",
        *indent(_odobj_t(obj) for obj in od.values()),
        "} ODObjs_t;",
        "",
        "static CO_PROGMEM ODObjs_t ODObjs = {",
        *indent(obj_lines(obj) for obj in od.values()),
        "};",
        "",
        "static OD_ATTR_OD OD_entry_t ODList[] = {",
        *indent(_odlist(obj) for obj in od.values()),
        *indent("{0x0000, 0x00, 0, NULL, NULL}"),
        "};",
        "",
        "static OD_t _OD = {",
        *indent("(sizeof(ODList) / sizeof(ODList[0])) - 1,"),
        *indent("&ODList[0]"),
        "};",
        "",
        "OD_t *OD = &_OD;",
    ]


def decl_type(obj: ODVariable, name: str) -> list[str]:
    """Generates a type declaration for an ODVariable"""

    ctype = DATA_TYPE_C_TYPES
    if obj.data_type == DOMAIN:
        return []  # skip domains
    if obj.data_type in (VISIBLE_STRING, UNICODE_STRING):
        return [
            f"{ctype[obj.data_type]} {name}[{len(cast(str, obj.default)) + 1}];",
        ]  # + 1 for '\0'
    if obj.data_type == OCTET_STRING:
        return [f"{ctype[obj.data_type]} {name}[{len(cast(bytes, obj.default))}];"]
    assert obj.data_type is not None
    return [f"{ctype[obj.data_type]} {name};"]


def _canopennode_h_lines(obj: ODVariable | ODRecord | ODArray) -> list[str]:
    """Generate struct lines for OD.h for a specific index"""

    if obj.index in _SKIP_INDEXES:
        return []

    name = f"x{obj.index:X}_{obj.name}"

    if isinstance(obj, ODVariable):
        return decl_type(obj, name)
    if isinstance(obj, ODArray):
        sub = next(islice(obj.values(), 1, None))
        return [
            f"uint8_t {name}_sub0;",
            *decl_type(sub, f"{name}[OD_CNT_ARR_{obj.index:X}]"),
        ]
    if isinstance(obj, ODRecord):
        lines = ["struct {"]
        for sub in obj.values():
            lines.extend(indent(decl_type(sub, sub.name)))
        lines.append(f"}} {name};")
        return lines
    raise TypeError(f"Invalid object {obj.name} type: {type(obj)}")


def _make_defines(obj: ODVariable | ODRecord | ODArray) -> list[str]:
    # add nice #defines for indexes and subindex values
    if obj.index < 0x2000:
        return []  # only care about common, card, and RPDO mapped objects

    lines = [f"#define OD_INDEX_{obj.name.upper()} 0x{obj.index:X}"]

    if not isinstance(obj, ODVariable):
        for j, sub in obj.items():
            if j == 0:
                continue
            sub_name = f"{obj.name}_{sub.name}"
            lines.append(f"#define OD_SUBINDEX_{sub_name.upper()} 0x{j:X}")
    lines.append("")
    return lines


def _obj_name(obj: ODVariable) -> str:
    if isinstance(obj.parent, ODRecord):
        return f"{obj.parent.name}_{obj.name}"
    if isinstance(obj.parent, ODArray):
        return obj.parent.name
    return obj.name


def _make_enum_lines(obj: ODVariable) -> list[str]:
    if not obj.value_descriptions:
        return []

    return [
        f"enum {_obj_name(obj)}_enum {{",
        *indent(
            f"{_obj_name(obj).upper()}_{name.upper()} = {value},"
            for value, name in obj.value_descriptions.items()
        ),
        "};",
        "",
    ]


def _make_enums(obj: ODVariable | ODRecord | ODArray) -> list[str]:
    if isinstance(obj, ODVariable):
        return _make_enum_lines(obj)
    if isinstance(obj, ODArray):
        return _make_enum_lines(next(islice(obj.values(), 1, None)))
    if isinstance(obj, ODRecord):
        return [line for sub in obj.values() for line in _make_enum_lines(sub)]
    raise TypeError(f"Invalid object {obj.name} type: {type(obj)}")


def _make_bitfields_lines(obj: ODVariable) -> list[str]:
    if not obj.bit_definitions:
        return []

    assert obj.data_type is not None
    data_type = DATA_TYPE_C_TYPES[obj.data_type]
    data_size = DATA_TYPE_C_SIZE[obj.data_type]
    bitfield_name = _obj_name(obj) + "_bitfield"

    lines = []
    total_bits = 0
    for name, bits in sorted(obj.bit_definitions.items(), key=lambda k: max(k[1])):
        if total_bits < min(bits):
            unused_bits = min(bits) - total_bits
            lines.append(f"{data_type} unused{total_bits} : {unused_bits};")
            total_bits += unused_bits
        lines.append(f"{data_type} {name.lower()} : {len(bits)};")
        total_bits += len(bits)

    if total_bits < data_size:
        unused_bits = data_size - total_bits
        lines.append(f"{data_type} unused{total_bits} : {unused_bits};")

    return [
        f"typedef union {bitfield_name} {{",
        *indent(
            f"{data_type} value;", "struct __attribute((packed)) {", *indent(lines), "} fields;"
        ),
        f"}} {bitfield_name}_t;",
        f"STATIC_ASSERT(sizeof({bitfield_name}_t) == sizeof({data_type}));",
        "",
    ]


def _make_bitfields(obj: ODVariable | ODRecord | ODArray) -> list[str]:
    if isinstance(obj, ODVariable):
        return _make_bitfields_lines(obj)
    if isinstance(obj, ODArray):
        return _make_bitfields_lines(next(islice(obj.values(), 1, None)))
    if isinstance(obj, ODRecord):
        return [line for sub in obj.values() for line in _make_bitfields_lines(sub)]
    raise TypeError(f"Invalid object {obj.name} type: {type(obj)}")


def generate_canopennode_h(od: canopen.ObjectDictionary) -> list[str]:
    """Transform an od into a CANopenNode OD.h file

    Parameters
    ----------
    od: canopen.ObjectDictionary
        od data structure to save as file
    """

    return [
        "#ifndef OD_H",
        "#define OD_H",
        "",
        "#include <assert.h>",
        "#include <stdbool.h>",
        "#include <stdint.h>",
        "#include <301/CO_ODinterface.h>",
        "",
        "#ifdef __cplusplus",
        "#ifndef _Static_assert",
        "#define _Static_assert static_assert",
        "#endif",
        "#endif",
        "",
        (
            '#define STATIC_ASSERT(expression) '
            '_Static_assert((expression), "(" #expression ") failed")'
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
        *(
            f"#define OD_CNT_ARR_{i:X} {len(obj) - 1}"
            for i, obj in od.items()
            if isinstance(obj, ODArray)
        ),
        "",
        "typedef struct {",
        *indent(_canopennode_h_lines(obj) for obj in od.values()),
        "} OD_RAM_t;",
        "",
        "#ifndef OD_ATTR_RAM",
        "#define OD_ATTR_RAM",
        "#endif",
        "extern OD_ATTR_RAM OD_RAM_t OD_RAM;",
        "",
        "#ifndef OD_ATTR_OD",
        "#define OD_ATTR_OD",
        "#endif",
        "extern OD_ATTR_OD OD_t *OD;",
        "",
        *(f"#define OD_ENTRY_H{i:X} &OD->list[{num}]" for num, i in enumerate(od)),
        "",
        *(
            f"#define OD_ENTRY_H{i:X}_{obj.name.upper()} &OD->list[{num}]"
            for num, (i, obj) in enumerate(od.items())
        ),
        "",
        *(line for obj in od.values() for line in _make_defines(obj)),
        *(line for obj in od.values() for line in _make_enums(obj)),
        *(line for obj in od.values() for line in _make_bitfields(obj)),
        "#endif /* OD_H */",
    ]


def gen_fw_files(args: Namespace) -> None:
    """generate CANopenNode firmware files main"""
    config = OreSatConfig(args.oresat)

    if args.dir_path.exists() and not args.dir_path.is_dir():
        print(f"'{args.dir_path}' already exists and is not a directory")
        return

    if args.card.lower() == 'base':
        od = config.fw_base_od
    else:
        try:
            od = config.od_db[config.name_from_alias(args.card)]
        except KeyError:
            print(f"invalid oresat card: {args.card}")
            return

    versions = od["versions"]
    assert isinstance(versions, ODRecord)
    if args.hardware_version is not None:
        versions["hw_version"].default = args.hardware_version
    if args.firmware_version is not None:
        versions["fw_version"].default = args.firmware_version

    odc, odh = generate_canopennode(od)

    args.dir_path.mkdir(parents=True, exist_ok=True)
    with (args.dir_path / "OD.c").open("w") as f:
        f.writelines(line + "\n" for line in odc)
    with (args.dir_path / "OD.h").open("w") as f:
        f.writelines(line + "\n" for line in odh)
