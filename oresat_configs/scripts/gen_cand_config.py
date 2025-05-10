import os

import canopen

from .._yaml_to_od import gen_od, load_od_configs, load_od_db
from ..configs.cards_config import CardsConfig
from ..configs.od_config import OdConfig
from .gen_dcf import make_dcf_objects_lines


def write_cand_od_config(od: canopen.ObjectDictionary):
    lines = ["[Objects]"]

    indexes = sorted(od.indices)

    lines.append(f"SupportedObjects={len(indexes)}")
    for index in indexes:
        num = indexes.index(index)
        lines.append(f"{num}=0x{index:X}")
    lines.append("")
    lines += make_dcf_objects_lines(od, indexes)

    with open("od.conf", "w") as f:
        for line in lines:
            f.write(line + "\n")


def gen_cand_od_config(od_config_path: str):
    od_config = OdConfig.from_yaml(od_config_path)
    od = gen_od([od_config])
    write_cand_od_config(od)


def gen_cand_manager_od_config(cards_config_path: str):
    cards_config = CardsConfig.from_yaml(cards_config_path)
    config_dir = os.path.dirname(cards_config_path)
    od_configs = load_od_configs(cards_config, config_dir)
    od_db = load_od_db(cards_config, od_configs)
    write_cand_od_config(od_db[cards_config.manager.name])


def gen_cand_card_config(name: str, node_id: int):
    lines = [
        "[Card]",
        f"Name={name}",
        f"NodeId=0x{node_id:X}",
    ]

    with open("card.conf", "w") as f:
        for line in lines:
            f.write(line + "\n")
