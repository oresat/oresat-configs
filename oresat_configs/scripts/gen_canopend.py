import os
from argparse import Namespace
from typing import Any

from canopen.objectdictionary import Array, ObjectDictionary, Variable

from .._yaml_to_od import DataType, gen_od
from ..configs.od_config import OdConfig
from . import INDENT4, snake_to_camel

GEN_CANOPEND = "generate od file for oresat linux apps"


def register_subparser(subparsers: Any):
    parser = subparsers.add_parser("canopend", help=GEN_CANOPEND)
    parser.description = GEN_CANOPEND
    parser.add_argument("name", help="name of node")
    parser.add_argument("config", help="path to od config")
    parser.add_argument(
        "-d", "--dir-path", default=".", help="directory path. default %(default)s"
    )
    parser.set_defaults(func=gen_canopend)


def make_enum_lines(name, enums) -> list[str]:
    lines = ["\n\n"]
    class_name = snake_to_camel(name)
    lines.append(f"class {class_name}(Enum):\n")
    for value, name in enums.items():
        lines.append(f"    {name.upper()} = {value}\n")
    return lines


def make_bitfield_lines(name, bitfields) -> list[str]:
    lines = ["\n\n"]
    class_name = snake_to_camel(name) + "BitField"
    lines.append(f"class {class_name}(EntryBitField):\n")
    for b_name, value in bitfields.items():
        if isinstance(value, int):
            value = [value]
        bits = len(value)
        offset = min(value)
        lines.append(f"    {b_name.upper()} = {offset}, {bits}\n")
    return lines


def write_canopend_od(
    name: str, od: ObjectDictionary, dir_path: str = ".", add_tpdos: bool = True
):
    enums = {}
    bitfields = {}
    entries = {}
    tpdos = []

    for index in sorted(od.indices):
        obj = od[index]

        if 0x1800 <= index < 0x1A00:
            tpdos.append(index - 0x1800)

        if index < 0x2000:
            continue

        if isinstance(obj, Variable):
            obj_name = obj.name
            entries[obj_name] = obj

            obj_name = f"{name}_{obj.name}"
            if obj.value_descriptions:
                enums[obj_name] = obj.value_descriptions
            if obj.bit_definitions:
                bitfields[obj_name] = obj.bit_definitions
        elif isinstance(obj, Array):
            sub1 = list(obj.subindices.values())[1]
            obj_name = f"{name}_{obj.name}"
            if sub1.value_descriptions:
                enums[obj_name] = sub1.value_descriptions
            if sub1.bit_definitions:
                bitfields[obj_name] = sub1.bit_definitions

            for sub_obj in obj.subindices.values():
                if sub_obj.subindex == 0:
                    continue

                obj_name = f"{obj.name}_{sub_obj.name}"
                entries[obj_name] = sub_obj
        else:  # Record
            for sub_obj in obj.subindices.values():
                if sub_obj.subindex == 0:
                    continue

                obj_name = f"{obj.name}_{sub_obj.name}"
                entries[obj_name] = sub_obj

                obj_name = f"{name}_{obj_name}"
                if sub_obj.value_descriptions:
                    enums[obj_name] = sub_obj.value_descriptions
                if sub_obj.bit_definitions:
                    bitfields[obj_name] = sub_obj.bit_definitions

    lines = [
        "from enum import Enum\n\n",
    ]

    line = "from oresat_libcanopend import DataType, Entry"
    if bitfields:
        line += ", EntryBitField"
    line += "\n"
    lines.append(line)

    for e_name, values in enums.items():
        lines += make_enum_lines(e_name, values)

    for b_name, values in bitfields.items():
        lines += make_bitfield_lines(b_name, values)

    lines.append("\n")
    lines.append("\n")
    node_name = snake_to_camel(name)
    lines.append(f"class {node_name}Entry(Entry):\n")
    for entry_name, obj in entries.items():
        dt = DataType(obj.data_type)

        class_name = obj.parent.name if isinstance(obj.parent, Array) else entry_name
        class_name = snake_to_camel(f"{name}_{class_name}")

        e_enum = None
        if obj.value_descriptions:
            e_enum = class_name

        bitfield = None
        if obj.bit_definitions:
            bitfield = f"{class_name}BitField"

        line = f"    {entry_name.upper()} = 0x{obj.index:X}, 0x{obj.subindex:X}, DataType.{dt.name}"
        default = obj.default
        if isinstance(default, str):
            default = f'"{default}"'
        line += f", {default}"

        if obj.min or obj.max or e_enum or bitfield:
            line += f", {obj.min}, {obj.max}, {e_enum}, {bitfield}"

        lines.append(line + "\n")

    if add_tpdos and len(tpdos) > 0:
        lines.append(f"\n\nclass {snake_to_camel(name)}Tpdo(Enum):\n")
        for i in range(len(tpdos)):
            lines.append(f"{INDENT4}TPDO_{tpdos[i] + 1} = {i}\n")

    if dir_path:
        os.makedirs(dir_path, exist_ok=True)

    output_file = os.path.join(dir_path, f"{name}_od.py")
    with open(output_file, "w") as f:
        f.writelines(lines)


def gen_canopend(args: Namespace):
    od_config = OdConfig.from_yaml(args.config)
    od = gen_od([od_config])
    write_canopend_od(args.name, od, args.dir_path)
