from __future__ import annotations

from pathlib import Path
from string import Template

from canopen.objectdictionary import Array, ObjectDictionary, Variable

from .._yaml_to_od import (
    TPDO_COMM_START,
    TPDO_PARA_START,
    DataType,
    gen_od,
    load_od_configs,
    load_od_db,
)
from ..configs.cards_config import CardInfo, CardsConfig
from ..configs.edl_config import EdlCommandConfig, EdlCommandFieldConfig, load_edl_config
from ..configs.mission_config import MissionConfig, pack_beacon_header
from ..configs.od_config import OdConfig
from . import (
    INDENT4,
    INDENT8,
    INDENT12,
    INDENT16,
    OTHER_STD_OBJS_START,
    RPDO_OBJS_START,
    __version__,
    snake_to_camel,
)
from .gen_cand import make_bitfield_lines, make_enum_lines, write_cand_od, write_cand_od_config

EDL_TEMPLATE = Path(__file__).parent / "edl_commands.py.txt"
CARDS_TEMPLATE = Path(__file__).parent / "cards.py.txt"

# custom struct-like formats for dynamic length strings and bytearrays
DYN_STR_FMT = "w"
DYN_BYTES_FMT = "y"

DT_2_STRUCT_FMT = {
    DataType.BOOL: "?",
    DataType.INT8: "b",
    DataType.INT16: "h",
    DataType.INT32: "i",
    DataType.INT64: "q",
    DataType.UINT8: "B",
    DataType.UINT16: "H",
    DataType.UINT32: "I",
    DataType.UINT64: "Q",
    DataType.OCTET_STR: DYN_BYTES_FMT,
    DataType.STR: DYN_STR_FMT,
}

DT_2_PY_TYPE = {
    DataType.BOOL: "bool",
    DataType.INT8: "int",
    DataType.INT16: "int",
    DataType.INT32: "int",
    DataType.INT64: "int",
    DataType.UINT8: "int",
    DataType.UINT16: "int",
    DataType.UINT32: "int",
    DataType.UINT64: "int",
    DataType.OCTET_STR: "bytes",
    DataType.STR: "str",
}


def write_cand_manager_od(
    name: str,
    od: ObjectDictionary,
    cards_config: CardsConfig,
    common_od_configs: dict[str, OdConfig],
    dir_path: Path | str | None = None,
) -> None:
    tpdos = []
    enums = {}
    bitfields = {}
    entries = {}

    if dir_path is None:
        dir_path = Path().cwd()
    if isinstance(dir_path, str):
        dir_path = Path(dir_path)

    imports = {card.base: [] for card in cards_config.cards}
    for i in common_od_configs:
        imports[i] = []

    common_indexes = []
    for c_name, common_od_config in common_od_configs.items():
        for obj in common_od_config.objects:
            obj_name = f"{c_name}_{obj.name}"
            if isinstance(obj.subindexes, list) and obj.subindexes:
                common_indexes.extend([f"{obj_name}_{sub_obj.name}" for sub_obj in obj.subindexes])
            else:
                common_indexes.append(obj_name)

    def get_card(obj_name: str) -> CardInfo:
        for card in cards_config.cards:
            if obj_name.startswith(card.name):
                return card
        return cards_config.manager

    for index in sorted(od.indices):
        obj = od[index]

        if TPDO_COMM_START <= index < TPDO_PARA_START:
            tpdos.append(index - TPDO_COMM_START)

        if index < OTHER_STD_OBJS_START:
            continue

        if isinstance(obj, Variable):
            obj_name = obj.name
            entries[obj_name] = obj

            if obj.index < RPDO_OBJS_START:
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
            if obj.index < RPDO_OBJS_START:
                obj_name = f"{name}_{obj.name}"
                if sub1.value_descriptions:
                    enums[obj_name] = sub1.value_descriptions
                if sub1.bit_definitions:
                    bitfields[obj_name] = sub1.bit_definitions
            else:
                obj_name = f"{name}_{obj.name}"
                card = get_card(obj_name)
                tmp = obj_name.replace(card.name, card.common)
                if tmp in common_indexes:
                    if sub1.value_descriptions:
                        imports[card.common].append(tmp)
                    if sub1.bit_definitions:
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

                if obj.index < RPDO_OBJS_START:
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
            ims = [snake_to_camel(i) for i in im]
            ims = sorted(set(ims))
            lines.append(f"from .{i_name}_od import {', '.join(ims)}\n")

    for e_name, values in enums.items():
        lines += make_enum_lines(e_name, values)

    for b_name, values in bitfields.items():
        lines += make_bitfield_lines(b_name, values)

    lines.append("\n")
    lines.append("\n")
    card_name = snake_to_camel(name)
    lines.append(f"class {card_name}Entry(Entry):\n")
    for entry_name, obj in entries.items():
        dt = DataType(obj.data_type)

        class_name = obj.parent.name if isinstance(obj.parent, Array) else entry_name
        if obj.index < RPDO_OBJS_START:
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

    dir_path.mkdir(parents=True, exist_ok=True)
    output_file = dir_path / f"{name}_od.py"
    with output_file.open("w") as f:
        f.writelines(lines)


def write_cand_mission_defs(
    card_name: str,
    mission_configs: list[MissionConfig],
    cards_config: CardsConfig,
    dir_path: str | Path,
) -> None:
    if isinstance(dir_path, str):
        dir_path = Path(dir_path)

    card_name_camel = snake_to_camel(card_name)
    mission_lines = [
        "from enum import Enum\n",
        "from dataclasses import dataclass\n",
        "\n",
        f"from ..{card_name}_od import {card_name_camel}Entry\n",
        "from ..cards import Card\n",
    ]

    for mission_config in mission_configs:
        name_upper = mission_config.name.upper()
        mission_lines.append(
            f"from .{mission_config.name} import {name_upper}_BEACON_HEADER, "
            f"{name_upper}_BEACON_BODY, {name_upper}_EDL_SCID, {name_upper}_CARDS\n"
        )

    mission_lines += [
        "\n\n",
        "@dataclass\n",
        "class MissionDef:\n",
        f"{INDENT4}nice_name: str\n",
        f"{INDENT4}id: int\n",
        f"{INDENT4}beacon_header: bytes\n",
        f"{INDENT4}beacon_body: list[C3Entry]\n",
        f"{INDENT4}edl_scid: int\n{INDENT4}cards: list[Card]\n",
        "\n\n",
    ]

    dir_path.mkdir(parents=True, exist_ok=True)
    mission_path = dir_path / "missions"
    mission_path.mkdir(parents=True, exist_ok=True)

    mission_lines.append("class Mission(MissionDef, Enum):\n")
    for mission_config in mission_configs:
        name_upper = mission_config.name.upper()
        mission_lines.append(
            f'{INDENT4}{name_upper} = "{mission_config.nice_name}", {mission_config.id}, '
            f"{name_upper}_BEACON_HEADER, {name_upper}_BEACON_BODY, "
            f"{name_upper}_EDL_SCID, {name_upper}_CARDS\n"
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
    output_file = mission_path / "__init__.py"
    with output_file.open("w") as f:
        f.writelines(mission_lines)

    manager_name = cards_config.manager.name

    for mission_config in mission_configs:
        name_upper = mission_config.name.upper()
        mission_lines = [
            "from ..cards import Card\n",
            f"from ..{manager_name}_od import {snake_to_camel(manager_name)}Entry\n\n",
            f"{name_upper}_EDL_SCID = 0x{mission_config.edl.spacecraft_id:X}\n\n",
        ]

        mission_lines.append(f"{name_upper}_CARDS = [\n")
        for card in cards_config.cards:
            if not card.missions or mission_config.name in card.missions:
                mission_lines.append(f"{INDENT8}Card.{card.name.upper()},\n")
        mission_lines.append("]\n")
        mission_lines.append("\n")

        header = pack_beacon_header(mission_config)
        mission_lines.append(f"{name_upper}_BEACON_HEADER = {header}\n\n")

        mission_lines.append(f"{name_upper}_BEACON_BODY = [\n")
        for names in mission_config.beacon.fields:
            mission_lines.append(f"{INDENT4}{card_name_camel}Entry.{'_'.join(names).upper()},\n")
        mission_lines.append("]\n")

        output_file = mission_path / f"{mission_config.name}.py"
        with output_file.open("w") as f:
            f.writelines(mission_lines)


def write_cand_fram_def(card: CardInfo, fram_def: list[list[str]], dir_path: str | Path) -> None:
    if isinstance(dir_path, str):
        dir_path = Path(dir_path)

    card_name_camel = snake_to_camel(card.name)
    fram_lines = [
        f"from .{card.name}_od import {card_name_camel}Entry\n",
        "\n\nFRAM_DEF = [\n",
    ]
    for names in fram_def:
        fram_lines.append(f"    {card_name_camel}Entry.{'_'.join(names).upper()},\n")
    fram_lines.append("]")

    dir_path.mkdir(parents=True, exist_ok=True)
    output_file = dir_path / "fram.py"
    with output_file.open("w") as f:
        f.writelines(fram_lines)


def write_cand_cards(cards_config: CardsConfig, dir_path: Path | str) -> None:
    if isinstance(dir_path, str):
        dir_path = Path(dir_path)

    with CARDS_TEMPLATE.open("r") as f:
        tpl = Template(f.read())

    card_processors = ""
    procs = {card.processor for card in cards_config.cards if card.processor.lower() != "none"}
    card_processors += "".join([f"{INDENT4}{p.upper()} = auto()\n" for p in procs])

    card_bases = ""
    for card_info in cards_config.configs:
        card_bases += f"{INDENT4}{card_info.name.upper()} = auto()\n"

    cards = ""
    for card in cards_config.cards:
        cards += (
            f"{INDENT4}{card.name.upper()} = 0x{card.node_id:X}, "
            f"CardProcessor.{card.processor.upper()}, "
            f"0x{card.opd_address:X}, {card.opd_always_on}"
        )
        base = card.base.upper() if card.base else "NONE"
        cards += f", CardBase.{base}"
        if card.child:
            cards += f", {card.child.upper()}"
        cards += "\n"

    out = tpl.substitute(card_processors=card_processors, card_bases=card_bases, cards=cards)

    dir_path.mkdir(parents=True, exist_ok=True)
    output_file = dir_path / "cards.py"
    with output_file.open("w") as f:
        f.write(out)


def write_cand_od_all(
    cards_config: CardsConfig, od_configs: dict[str, OdConfig], dir_path: Path | str
) -> None:
    if isinstance(dir_path, str):
        dir_path = Path(dir_path)

    dir_path.mkdir(parents=True, exist_ok=True)
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
    write_cand_od_config(od_db[cards_config.manager.name], dir_path)


def _join_fmts(fmts: list[str]) -> list[str]:
    new_fmts = []
    tmp = ""
    for fmt in fmts:
        if fmt in [DYN_BYTES_FMT, DYN_STR_FMT]:
            if tmp:
                new_fmts.append(tmp)
                tmp = ""
            new_fmts.append(fmt)
        else:
            tmp += fmt
    if tmp:
        new_fmts.append(tmp)
    return new_fmts


def _make_msg_class(name: str, cmd_id: int, fields: list[EdlCommandFieldConfig]) -> str:
    def dt2fmt(data_type: str) -> str:
        return DT_2_STRUCT_FMT[DataType[data_type.upper()]]

    def dt2py(data_type: str) -> str:
        return DT_2_PY_TYPE[DataType[data_type.upper()]]

    fmts = [dt2fmt(field.data_type) for field in fields]
    fmts = _join_fmts(fmts)
    return (
        f"@dataclass\n"
        f"class {name}(EdlMessage):\n"
        f"{INDENT4}_fmt: ClassVar[list[str]] = {fmts}\n"
        + "".join([f"{INDENT4}{field.name}: {dt2py(field.data_type)}\n" for field in fields])
        + "\n\n"
    )


def write_cand_edl_def(edl_config: list[EdlCommandConfig], dir_path: Path | str) -> None:
    if isinstance(dir_path, str):
        dir_path = Path(dir_path)

    with EDL_TEMPLATE.open("r") as f:
        tpl = Template(f.read())

    req_msgs = ""
    res_msgs = ""
    cmd_enums = ""
    cmd_table = ""

    for e in edl_config:
        req_name = "None"
        res_name = "None"
        cmd_enums += f"{INDENT4}{e.name.upper()} = 0x{edl_config.index(e):X}\n"
        if e.request:
            req_name = f"{snake_to_camel(e.name)}EdlRequest"
            req_msgs += _make_msg_class(req_name, e.id, e.request)
        if e.response:
            res_name = f"{snake_to_camel(e.name)}EdlResponse"
            res_msgs += _make_msg_class(res_name, e.id, e.response)
        cmd_table += (
            f"{INDENT4}EdlCommandId.{e.name.upper()}: EdlCommand({req_name}, {res_name}),\n"
        )

    out = tpl.substitute(
        dyn_str_fmt=DYN_STR_FMT,
        dyn_bytes_fmt=DYN_BYTES_FMT,
        req_msgs=req_msgs[:-1],
        res_msgs=res_msgs[:-1],
        cmd_enums=cmd_enums,
        cmd_table=cmd_table[:-1],
    )

    file_path = dir_path / "edl_commands.py"
    with file_path.open("w") as f:
        f.write(out)

    dir_path.mkdir(parents=True, exist_ok=True)


def gen_cand_manager_files(
    cards_config_path: Path | str,
    mission_config_paths: list[Path] | list[str],
    edl_config_path: Path | str,
    dir_path: Path | str,
) -> None:
    if isinstance(cards_config_path, str):
        cards_config_path = Path(cards_config_path)
    if isinstance(edl_config_path, str):
        edl_config_path = Path(edl_config_path)
    if isinstance(dir_path, str):
        dir_path = Path(dir_path)

    edl_config = load_edl_config(edl_config_path)
    cards_config = CardsConfig.from_yaml(cards_config_path)
    mission_configs = [MissionConfig.from_yaml(m) for m in mission_config_paths]
    config_dir = cards_config_path.parent

    dir_path.mkdir(parents=True, exist_ok=True)
    init_file = dir_path / "__init__.py"
    if not init_file.exists():
        init_file.touch()

    od_configs = load_od_configs(cards_config, config_dir)
    write_cand_od_all(cards_config, od_configs, dir_path)
    manager_name = cards_config.manager.name
    write_cand_mission_defs(manager_name, mission_configs, cards_config, dir_path)
    write_cand_fram_def(cards_config.manager, od_configs[manager_name].fram, dir_path)
    write_cand_cards(cards_config, dir_path)
    write_cand_edl_def(edl_config, dir_path)
