from __future__ import annotations

from pathlib import Path

from canopen.objectdictionary import Array, ObjectDictionary, Record, Variable

from .._yaml_to_od import DataType, gen_od, load_od_configs, load_od_db
from ..configs.cards_config import CardsConfig
from ..configs.od_config import OdConfig


def write_cand_od_config(od: ObjectDictionary) -> None:
    lines = ["[Objects]"]

    indexes = sorted(od.indices)

    lines.append(f"SupportedObjects={len(indexes)}")
    for index in indexes:
        num = indexes.index(index)
        lines.append(f"{num}=0x{index:X}")
    lines.append("")
    lines += make_objects_lines(od, indexes)

    with Path("od.conf").open("w") as f:
        for line in lines:
            f.write(line + "\n")


def make_objects_lines(od: ObjectDictionary, indexes: list[int]) -> list[str]:
    lines = []

    for i in indexes:
        obj = od[i]
        if isinstance(obj, Variable):
            lines += make_variable_lines(obj, i)
        elif isinstance(obj, Array):
            lines += make_array_lines(obj, i)
        elif isinstance(obj, Record):
            lines += make_record_lines(obj, i)

    return lines


def make_variable_lines(variable: Variable, index: int, subindex: int | None = None) -> list[str]:
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
        if variable.data_type == DataType.OCTET_STR:
            tmp = variable.default.hex()
            lines.append(f"DefaultValue={tmp}")
        else:
            lines.append(f"DefaultValue={variable.default}")
    if variable.pdo_mappable:  # optional
        lines.append(f"PDOMapping={int(variable.pdo_mappable)}")
    lines.append("")

    return lines


def make_array_lines(array: Array, index: int) -> list[str]:
    lines = []

    lines.append(f"[{index:X}]")

    lines.append(f"ParameterName={array.name}")
    lines.append("ObjectType=0x08")
    lines.append(f"SubNumber={len(array)}")
    lines.append("")

    for i in array.subindices:
        lines += make_variable_lines(array[i], index, i)

    return lines


def make_record_lines(record: Record, index: int) -> list[str]:
    lines = []

    lines.append(f"[{index:X}]")

    lines.append(f"ParameterName={record.name}")
    lines.append("ObjectType=0x09")
    lines.append(f"SubNumber={len(record)}")
    lines.append("")

    for i in record.subindices:
        lines += make_variable_lines(record[i], index, i)

    return lines


def gen_cand_od_config(od_config_path: Path | str) -> None:
    if isinstance(od_config_path, str):
        od_config_path = Path(od_config_path)
    od_config = OdConfig.from_yaml(od_config_path)
    od = gen_od([od_config])
    write_cand_od_config(od)


def gen_cand_manager_od_config(cards_config_path: Path | str) -> None:
    if isinstance(cards_config_path, str):
        cards_config_path = Path(cards_config_path)
    cards_config = CardsConfig.from_yaml(cards_config_path)
    od_configs = load_od_configs(cards_config, cards_config_path.parent)
    od_db = load_od_db(cards_config, od_configs)
    write_cand_od_config(od_db[cards_config.manager.name])
