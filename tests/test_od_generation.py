'''Test that the yaml to od conversion works as expected'''

from importlib import resources

from oresat_configs import OreSatConfig
from oresat_configs.card_config import CardConfig


class TestOdGeneration:
    def test_tpdo_overlay(self, config: OreSatConfig) -> None:
        # For every overlay tpdo, check that it ends up exactly in the final config
        for name, overlay_path in config.mission.overlays.items():
            with resources.as_file(overlay_path) as path:
                overlay = CardConfig.from_yaml(path)
            for cardname, cfg in config.configs.items():
                if cardname.startswith(name):
                    for tpdo in overlay.tpdos:
                        assert tpdo in cfg.tpdos

    def test_rpdo_overlay(self, config: OreSatConfig) -> None:
        # For every overlay rpdo, check that it ends up exactly in the final config
        for name, overlay_path in config.mission.overlays.items():
            with resources.as_file(overlay_path) as path:
                overlay = CardConfig.from_yaml(path)
            for cardname, cfg in config.configs.items():
                if cardname.startswith(name):
                    for tpdo in overlay.rpdos:
                        assert tpdo in cfg.rpdos
