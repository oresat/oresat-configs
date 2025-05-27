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

from dataclasses import dataclass
from importlib.resources import as_file
from typing import Union

from ._yaml_to_od import (
    _gen_c3_beacon_defs,
    _gen_c3_fram_defs,
    _gen_fw_base_od,
    _gen_od_db,
    _load_configs,
)
from .beacon_config import BeaconConfig
from .card_info import Card, cards_from_csv
from .constants import Mission, __version__

__all__ = ["Card", "Mission", "__version__"]


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
        self.configs = _load_configs(self.cards, self.mission.overlays)
        self.od_db = _gen_od_db(self.mission, self.cards, beacon_config, self.configs)
        c3_od = self.od_db["c3"]
        self.beacon_def = _gen_c3_beacon_defs(c3_od, beacon_config)
        self.fram_def = _gen_c3_fram_defs(c3_od, self.configs["c3"])
        self.fw_base_od = _gen_fw_base_od(self.mission)
