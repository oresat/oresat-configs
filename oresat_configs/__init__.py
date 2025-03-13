"""OreSat OD database"""

# Checks that pyyaml is installed correctly. For performance reasons it must use the libyaml C
# bindings. To use them both libyaml must be installed on the local system, and pyyaml must have
# been built to use them. This works correctly on x86 systems, but on arm pyyaml is built by
# default to not include the bindings.
try:
    from yaml import CLoader
except ImportError as e:
    raise ImportError(
        "pyyaml missing/installed without libyaml bindings. See oresat-configs README.md for more"
    ) from e

import os
from importlib.resources import as_file
from typing import Union

from ._yaml_to_od import gen_master_od, gen_od, get_beacon_defs, get_fram_defs, set_od_node_id
from .beacon_config import BeaconConfig
from .card_info import Card, cards_from_csv
from .constants import Mission, __version__
from .od_config import OdConfig

__all__ = ["Card", "Mission", "__version__"]

DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = DIR + "/base"


class OreSatConfig:
    """All the configs for an OreSat mission."""

    def __init__(self, mission: Union[Mission, str, None] = None):
        """The parameter mission may be:
        - a string, either short or long mission name ('0', 'OreSat0.5', ...)
        - a Mission (ORESAT0, ...)
        - Omitted or None, in which case Mission.default() is chosen

        It will be used to derive the appropriate Mission, the collection of
        constants associated with a specific oresat mission.
        """
        if mission is None:
            self.mission = Mission.default()
        elif isinstance(mission, str):
            self.mission = Mission.from_string(mission)
        elif isinstance(mission, Mission):
            self.mission = mission
        else:
            raise TypeError(f"Unsupported mission type: '{type(mission)}'")

        with as_file(self.mission.beacon) as path:
            beacon_config = BeaconConfig.from_yaml(path)
        with as_file(self.mission.cards) as path:
            self.cards = cards_from_csv(path)

        od_configs = {}
        for config_file in os.listdir(BASE_DIR):
            name = config_file.split(".")[0]
            od_configs[name] = OdConfig.from_yaml(os.path.join(BASE_DIR, config_file))

        self.od_db = {}
        for name, card in self.cards.items():
            if name == "c3" or card.processor == "none":
                continue

            if card.processor == "stm32":
                od = gen_od([od_configs["fw_common"], od_configs[card.base]])
            elif card.processor == "octavo":
                od = gen_od([od_configs["sw_common"], od_configs[card.base]])
            set_od_node_id(od, card.node_id)
            self.od_db[name] = od

        c3_od = gen_master_od([od_configs["sw_common"], od_configs["c3"]], self.od_db)
        self.od_db["c3"] = c3_od
        self.fram_def = get_fram_defs(c3_od, od_configs["c3"])
        self.beacon_def = get_beacon_defs(c3_od, beacon_config)

        self.fw_base_od = gen_od([od_configs["fw_common"]])
