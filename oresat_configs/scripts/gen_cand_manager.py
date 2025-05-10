import os
from typing import Optional

from canopen.objectdictionary import Array, ObjectDictionary, Variable

from .._yaml_to_od import DataType, gen_od, load_od_configs, load_od_db
from ..configs.cards_config import CardInfo, CardsConfig
from ..configs.mission_config import MissionConfig, pack_beacon_header
from ..configs.od_config import OdConfig
from . import INDENT4, INDENT8, INDENT12, INDENT16, __version__, snake_to_camel
from .gen_cand import make_bitfield_lines, make_enum_lines, write_cand_od


def write_cand_manager_od(
    name: str,
    od: ObjectDictionary,
    cards_config: Optional[CardsConfig],
    common_od_configs: dict[str, OdConfig],
    dir_path: str = ".",
):
    tpdos = []
    enums = {}
    bitfields = {}
    entries = {}

    imports = {card.base: [] for card in cards_config.cards}
    for i in common_od_configs:
        imports[i] = []

    common_indexes = []
    for c_name, common_od_config in common_od_configs.items():
        for obj in common_od_config.objects:
            if isinstance(obj.subindexes, list) and obj.subindexes:
                for sub_obj in obj.subindexes:
                    common_indexes.append(f"{c_name}_{obj.name}_{sub_obj.name}")
            else:
                common_indexes.append(f"{c_name}_{obj.name}")

    def get_card(obj_name: str) -> CardInfo:
        for card in cards_config.cards:
            if obj_name.startswith(card.name):
                return card
        return cards_config.manager

    for index in sorted(od.indices):
        obj = od[index]

        if 0x1800 <= index < 0x1A00:
            tpdos.append(index - 0x1800)

        if index < 0x2000:
            continue

        if isinstance(obj, Variable):
            obj_name = obj.name
            entries[obj_name] = obj

            if obj.index < 0x5000:
                obj_name = f"{name}_{obj.name}"
                if obj.value_descriptions:
                    enums[obj_name] = obj.value_descriptions
                if obj.bit_definitions:
                    bitfields[obj_name] = obj.bit_definitions
            else:
                card = get_card(obj_name)

                tmp = obj_name.replace(card.name, card.common)
                if tmp in common_indexes:
                    if obj.value_descriptions:
                        imports[card.common].append(tmp)
                    if obj.bit_definitions:
                        imports[card.common].append(tmp + "_bit_field")
                else:
                    obj_name = obj_name.replace(card.name, card.base)
                    if obj.value_descriptions:
                        imports[card.base].append(obj_name)
                    if obj.bit_definitions:
                        imports[card.base].append(obj_name + "_bit_field")
        elif isinstance(obj, Array):
            sub1 = list(obj.subindices.values())[1]
            if obj.index < 0x5000:
                obj_name = f"{name}_{obj.name}"
                if sub1.value_descriptions:
                    enums[obj_name] = sub1.value_descriptions
                if sub1.bit_definitions:
                    bitfields[obj_name] = sub1.bit_definitions
            else:
                card = get_card(obj_name)
                tmp = obj_name.replace(card.name, card.common)
                if tmp in common_indexes:
                    if obj.value_descriptions:
                        imports[card.common].append(tmp)
                    if obj.bit_definitions:
                        imports[card.common].append(tmp + "_bit_field")
                else:
                    obj_name = obj_name.replace(card.name, card.base)
                    if sub1.value_descriptions:
                        imports[card.base].append(obj_name)
                    if sub1.bit_definitions:
                        imports[card.base].append(obj_name + "_bit_field")

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

                if obj.index < 0x5000:
                    obj_name = f"{name}_{obj_name}"
                    if sub_obj.value_descriptions:
                        enums[obj_name] = sub_obj.value_descriptions
                    if sub_obj.bit_definitions:
                        bitfields[obj_name] = sub_obj.bit_definitions
                else:
                    card = get_card(obj_name)
                    tmp = obj_name.replace(card.name, card.common)
                    if tmp in common_indexes:
                        if sub_obj.value_descriptions:
                            imports[card.common].append(tmp)
                        if sub_obj.bit_definitions:
                            imports[card.common].append(tmp + "_bit_field")
                    else:
                        obj_name = obj_name.replace(card.name, card.base)
                        if sub_obj.value_descriptions:
                            imports[card.base].append(obj_name)
                        if sub_obj.bit_definitions:
                            imports[card.base].append(obj_name + "_bit_field")

    lines = [
        f'"""generated by oresat-configs v{__version__}"""\n\n',
        "from enum import Enum\n\n",
    ]

    line = "from oresat_cand import DataType, Entry"
    if bitfields:
        line += ", EntryBitField"
    line += "\n"
    lines.append(line)

    if imports:
        lines.append("\n")
    for i_name, im in imports.items():
        if im:
            im = [snake_to_camel(i) for i in im]
            im = sorted(list(set(im)))
            lines.append(f"from .{i_name}_od import {', '.join(im)}\n")

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
        if obj.index < 0x5000:
            class_name = snake_to_camel(f"{name}_{class_name}")
        else:
            card = get_card(class_name)
            tmp = class_name.replace(card.name, card.common)
            if tmp in common_indexes:
                class_name = snake_to_camel(tmp)
            else:
                class_name = snake_to_camel(entry_name.replace(card.name, card.base))

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

    if len(tpdos) > 0:
        lines.append(f"\n\nclass {snake_to_camel(name)}Tpdo(Enum):\n")
        for i in range(len(tpdos)):
            lines.append(f"{INDENT4}TPDO_{tpdos[i] + 1} = {i}\n")

    if dir_path:
        os.makedirs(dir_path, exist_ok=True)

    output_file = os.path.join(dir_path, f"{name}_od.py")
    with open(output_file, "w") as f:
        f.writelines(lines)


def write_cand_mission_defs(
    node_name: str,
    mission_configs: list[MissionConfig],
    cards_config: CardsConfig,
    dir_path: str,
):
    node_name_camel = snake_to_camel(node_name)
    mission_lines = [
        "from enum import Enum\n",
        "from dataclasses import dataclass\n",
        "\n",
        f"from ..{node_name}_od import {node_name_camel}Entry\n",
        "from ..nodes import Node\n",
    ]

    for mission_config in mission_configs:
        name_upper = mission_config.name.upper()
        mission_lines.append(
            f"from .{mission_config.name} import {name_upper}_BEACON_HEADER, "
            f"{name_upper}_BEACON_BODY, {name_upper}_NODES\n"
        )

    mission_lines += [
        "\n\n",
        "@dataclass\n",
        "class MissionDef:\n",
        f"{INDENT4}nice_name: str\n",
        f"{INDENT4}id: int\n",
        f"{INDENT4}header: bytes\n",
        f"{INDENT4}body: list[C3Entry]\n",
        f"{INDENT4}nodes: list[Node]\n",
        "\n\n",
    ]

    os.makedirs(dir_path, exist_ok=True)
    mission_path = os.path.join(dir_path, "missions")
    if not os.path.isdir(mission_path):
        os.makedirs(mission_path, exist_ok=True)

    mission_lines.append("class Mission(MissionDef, Enum):\n")
    for mission_config in mission_configs:
        name_upper = mission_config.name.upper()
        mission_lines.append(
            f'{INDENT4}{name_upper} = "{mission_config.nice_name}", {mission_config.id}, '
            f"{name_upper}_BEACON_HEADER, "
            f"{name_upper}_BEACON_BODY, {name_upper}_NODES\n"
        )
    mission_lines += [
        "\n",
        f"{INDENT4}@classmethod\n",
        f"{INDENT4}def from_id(cls, mission_id: int):\n",
        f"{INDENT8}for m in cls:\n",
        f"{INDENT12}if mission_id == m.id:\n",
        f"{INDENT16}return m\n",
        f"{INDENT8}raise ValueError('invald mission id')\n",
    ]
    output_file = os.path.join(mission_path, "__init__.py")
    with open(output_file, "w") as f:
        f.writelines(mission_lines)

    manager_name = cards_config.manager.name

    for mission_config in mission_configs:
        name_upper = mission_config.name.upper()
        mission_lines = [
            "from ..nodes import Node\n",
            f"from ..{manager_name}_od import {snake_to_camel(manager_name)}Entry\n\n",
        ]

        mission_lines.append(f"{name_upper}_NODES = [\n")
        for card in cards_config.cards:
            if not card.missions or mission_config.name in card.missions:
                mission_lines.append(f"{INDENT8}Node.{card.name.upper()},\n")
        mission_lines.append("]\n")
        mission_lines.append("\n")

        header = pack_beacon_header(mission_config)
        mission_lines.append(f"{name_upper}_BEACON_HEADER = {header}\n\n")

        mission_lines.append(f"{name_upper}_BEACON_BODY = [\n")
        for names in mission_config.beacon.fields:
            mission_lines.append(f"{INDENT4}{node_name_camel}Entry.{'_'.join(names).upper()},\n")
        mission_lines.append("]\n")

        output_file = os.path.join(mission_path, f"{mission_config.name}.py")
        with open(output_file, "w") as f:
            f.writelines(mission_lines)


def write_cand_fram_def(card: CardInfo, fram_def: list[Variable], dir_path: str):
    node_name_camel = snake_to_camel(card.name)
    fram_lines = [
        f"from .{card.name}_od import {node_name_camel}Entry\n",
        "\n\nFRAM_DEF = [\n",
    ]
    for names in fram_def:
        fram_lines.append(f"    {node_name_camel}Entry.{'_'.join(names).upper()},\n")
    fram_lines.append("]")

    os.makedirs(dir_path, exist_ok=True)
    output_file = os.path.join(dir_path, "fram.py")
    with open(output_file, "w") as f:
        f.writelines(fram_lines)


def write_cand_nodes(cards_config: CardsConfig, dir_path: str):
    lines = [
        "from dataclasses import dataclass\n",
        "from enum import Enum, auto\n",
        "\n\n",
        "class NodeProcessor(Enum):\n",
        f"{INDENT4}NONE = 0\n",
        f"{INDENT4}STM32 = auto()\n",
        f"{INDENT4}OCTAVO = auto()\n",
        "\n\n",
    ]

    lines.append("class NodeBase(Enum):\n")
    lines.append(f"{INDENT4}NONE = 0\n")
    for card_info in cards_config.configs:
        lines.append(f"{INDENT4}{card_info.name.upper()} = auto()\n")

    lines += [
        "\n\n",
        "@dataclass\n",
        "class NodeDef:\n",
        f"{INDENT4}node_id: int\n",
        f"{INDENT4}processor: NodeProcessor\n",
        f"{INDENT4}opd_address: int\n",
        f"{INDENT4}opd_always_on: bool\n",
        f"{INDENT4}base: NodeBase\n",
        f'{INDENT4}child: str = ""\n',
    ]

    lines.append("\n\nclass Node(NodeDef, Enum):\n")
    for card in cards_config.cards:
        line = (
            f"{INDENT4}{card.name.upper()} = 0x{card.node_id:X}, "
            f"NodeProcessor.{card.processor.upper()}, "
            f"0x{card.opd_address:X}, {card.opd_always_on}"
        )
        base = card.base.upper() if card.base else "NONE"
        line += f", NodeBase.{base}"
        if card.child:
            line += f", {card.child.upper()}"
        lines.append(line + "\n")

    os.makedirs(dir_path, exist_ok=True)
    output_file = os.path.join(dir_path, "nodes.py")
    with open(output_file, "w") as f:
        f.writelines(lines)


def write_cand_od_all(cards_config: CardsConfig, od_configs: dict[str, OdConfig], dir_path: str):
    os.makedirs(dir_path, exist_ok=True)
    for name, od_config in od_configs.items():
        od = gen_od([od_config])
        write_cand_od(name, od, dir_path, add_tpdos=False)
    od_db = load_od_db(cards_config, od_configs)

    common_od_configs = {}
    for card in cards_config.cards:
        if card.common:
            common_od_configs[card.common] = od_configs[card.common]

    write_cand_manager_od(
        cards_config.manager.name,
        od_db[cards_config.manager.name],
        cards_config,
        common_od_configs,
        dir_path,
    )


def gen_cand_manager_files(cards_config_path: str, mission_config_paths: list[str], dir_path: str):
    cards_config = CardsConfig.from_yaml(cards_config_path)
    mission_configs = [MissionConfig.from_yaml(m) for m in mission_config_paths]
    config_dir = os.path.dirname(cards_config_path)

    os.makedirs(dir_path, exist_ok=True)
    init_file = os.path.join(dir_path, "__init__.py")
    if not os.path.isfile(init_file):
        open(init_file, "w").close()

    od_configs = load_od_configs(cards_config, config_dir)
    write_cand_od_all(cards_config, od_configs, dir_path)
    manager_name = cards_config.manager.name
    write_cand_mission_defs(manager_name, mission_configs, cards_config, dir_path)
    write_cand_fram_def(cards_config.manager, od_configs[manager_name].fram, dir_path)
    write_cand_nodes(cards_config, dir_path)
