"""Unit tests for ensuring yaml config files match up with corresponding dataclasses"""

from importlib import abc, resources
from typing import Any

from dacite import Config, from_dict
from yaml import CLoader, load

from oresat_configs import Mission, _yaml_to_od, base
from oresat_configs.beacon_config import BeaconConfig
from oresat_configs.card_config import CardConfig, IndexObject


class TestConfigTypes:
    """Tests for yaml config files

    For each yaml config there should be a test that turns it into a dataclass but not
    necessarily the other way around. There are dataclasses that don't correspond to a config or
    only a portion of the config.
    """

    @staticmethod
    def load_yaml(path: abc.Traversable) -> Any:
        """Helper that wraps loading yaml from a path"""
        with path.open() as f:
            config = f.read()
        return load(config, Loader=CLoader)

    def test_beacon_config(self, mission: Mission) -> None:
        """Tests all the beacon configs, with dataclass BeaconConfig"""
        from_dict(
            BeaconConfig,
            self.load_yaml(mission.beacon),
            Config(strict=True, strict_unions_match=True),
        )

    def test_card_config(self, mission: Mission) -> None:
        """Tests all the card configs, with dataclass CardConfig"""
        card_paths = [f for f in resources.files(base).iterdir() if f.name.endswith(".yaml")]
        card_paths.extend(mission.overlays.values())
        for path in card_paths:
            from_dict(CardConfig, self.load_yaml(path), Config(strict=True))

    def test_standard_types(self) -> None:
        """Tests the standard objects config. Each entry gets its own IndexObject"""
        path = _yaml_to_od.STD_OBJS_FILE_NAME
        for data in self.load_yaml(path):
            from_dict(IndexObject, data, Config(strict=True))
