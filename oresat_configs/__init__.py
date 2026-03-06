"""OreSat OD database"""

from __future__ import annotations

# Checks that pyyaml is installed correctly. For performance reasons it must use the libyaml C
# bindings. To use them both libyaml must be installed on the local system, and pyyaml must have
# been built to use them. This works correctly on x86 systems, but on arm pyyaml is built by
# default to not include the bindings.
import yaml

if not hasattr(yaml, "CLoader"):
    raise ImportError("pyyaml installed without libyaml bindings. See oresat-configs README.md")

from importlib.resources import as_file

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

    def __init__(self, mission: Mission | str | None = None) -> None:
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

    def name_from_alias(self, card: str, number: int = 1) -> str:
        '''Finds the canonical card name from a given alias.

        Intended for the --card option in scripts, this will take a wide array of names and return
        the corresponding key that will find that card's config in od_db. For cards with number
        suffixes if the name is given without a number it defaults to the first card of that type,
        with the _1 suffix. For example:
        - battery -> battey_1
        - st -> star_tracker_1
        - solar_1 -> solar_1
        - gps -> gps

        Parameters
        ----------
        card
            The name or alias of a card to find in the od_db.
        num
            (optional) For cards with multiple copies this spefifies which one. Ignored if given as
            part of the card argument.

        Returns
        -------
            A name suitable as a key in od_db.

        Raises
        ------
        KeyError
            If no suitable name is found for the given alias.
        '''
        card_aliases = {name: name for name in self.cards}
        # FIXME: should be part of yaml. It's a big change to wire that up though
        # FIXME: should only include cards from current mission. This isn't technically bad
        #        since it'll KeyError anyway. Moving this to yaml will fix it.
        for name, aliases in {
            "battery": ["bat", "batt"],
            "solar": ["sol", "solar_module"],
            "adcs": ["imu"],
            "rw": ["reaction_wheel"],
            "diode_test": ["diode", "dtc"],
            "cfc_processor": ["cfc"],
            "star_tracker": ["st", "star_track"],
        }.items():
            canonical_name = name
            if name not in self.cards and f'{name}_{number}' in self.cards:
                canonical_name = f'{name}_{number}'
            card_aliases[name] = canonical_name
            for alias in aliases:
                card_aliases[alias] = canonical_name

        name = card_aliases[card.lower().replace("-", "_")]
        if name in self.cards:
            return name
        raise KeyError(f"No alias for '{name}' found")
