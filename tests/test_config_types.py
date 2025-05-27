"""Unit tests for ensuring yaml config files match up with corresponding dataclasses"""

import unittest
from importlib import abc, resources
from typing import Any

from dacite import from_dict  # , Config
from yaml import Loader, load

from oresat_configs import _yaml_to_od, base
from oresat_configs.beacon_config import BeaconConfig
from oresat_configs.card_config import CardConfig, IndexObject
from oresat_configs.constants import Mission


class ConfigTypes(unittest.TestCase):
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
        return load(config, Loader=Loader)

    def dtype_subtest(self, path: abc.Traversable, dtype: Any, data: Any) -> None:
        """The main check that gets done, creates a new subtest for each check"""
        with self.subTest(path=path, dtype=dtype):
            # raises WrongTypeError if the types don't check out
            # when we're ready, use the config below to ensure every yaml field is consumed
            from_dict(dtype, data)  # , Config(strict=True, strict_unions_match=True))

    def check_types(self, path: abc.Traversable, dtype: Any) -> None:
        """Helper that combines load_yaml() and dtype_subtest()"""
        self.dtype_subtest(path, dtype, self.load_yaml(path))

    def test_beacon_config(self) -> None:
        """Tests all the beacon configs, with dataclass BeaconConfig"""
        beacon_paths = [m.beacon for m in Mission]
        for path in beacon_paths:
            self.check_types(path, BeaconConfig)

    def test_card_config(self) -> None:
        """Tests all the card configs, with dataclass CardConfig"""
        card_paths = [f for f in resources.files(base).iterdir() if f.name.endswith(".yaml")]
        for m in Mission:
            card_paths.extend(m.overlays.values())
        for path in card_paths:
            self.check_types(path, CardConfig)

    def test_standard_types(self) -> None:
        """Tests the standard objects config. Each entry gets its own IndexObject"""
        path = _yaml_to_od.STD_OBJS_FILE_NAME
        for data in self.load_yaml(path):
            self.dtype_subtest(path, IndexObject, data)
