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
from typing import Union

from ._yaml_to_od import (
    _gen_c3_beacon_defs,
    _gen_c3_fram_defs,
    _gen_fw_base_od,
    _gen_od_db,
    _load_configs,
)
from .base import FW_COMMON_CONFIG_PATH
from .beacon_config import BeaconConfig
from .card_info import Card, cards_from_csv
from .constants import Consts, NodeId, OreSatId, __version__
from .edl_cmd_defs import EdlCommandDefinition, EdlCommandDefinitions, EdlCommandField

__all__ = ["Card", "Consts", "NodeId", "OreSatId", "__version__"]


class OreSatConfig:
    """All the configs for an OreSat mission."""

    def __init__(self, mission: Union[OreSatId, Consts, str]):
        """The parameter mission may be:
        - a string, either short or long mission name ('0', 'OreSat0.5', ...)
        - an OreSatId (ORESAT0, ...)
        - a Consts (ORESAT0, ...)

        It will be used to derive the appropriate Consts, the collection of
        constants associated with a specific oresat mission.
        """
        if isinstance(mission, str):
            mission = Consts.from_string(mission)
        elif isinstance(mission, OreSatId):
            mission = Consts.from_id(mission)
        elif not isinstance(mission, Consts):
            raise TypeError(f"Unsupported mission type: '{type(mission)}'")

        self.mission = mission
        beacon_config = BeaconConfig.from_yaml(mission.beacon_path)
        self.cards = cards_from_csv(mission)
        self.configs = _load_configs(mission.cards_path)
        self.od_db = _gen_od_db(mission, self.cards, beacon_config, self.configs)
        c3_od = self.od_db["c3"]
        self.beacon_def = _gen_c3_beacon_defs(c3_od, beacon_config)
        self.fram_def = _gen_c3_fram_defs(c3_od, self.configs["c3"])
        self.fw_base_od = _gen_fw_base_od(mission, FW_COMMON_CONFIG_PATH)

        # edl commands definitions
        node_ids = {}
        opd_addrs = {}
        for name in self.configs:
            card = self.cards[name]
            if card.node_id != 0:
                node_ids[name] = card.node_id
            if card.opd_address != 0:
                opd_addrs[name] = card.opd_address
        custom_enums = {
            "node_id": node_ids,
            "opd_addr": opd_addrs,
        }
        edl_file_path = f"{os.path.dirname(os.path.abspath(__file__))}/edl_cmd_defs.yaml"
        self.edl_cmd_defs = EdlCommandDefinitions(edl_file_path, custom_enums)
