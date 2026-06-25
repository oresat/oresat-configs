from oresat_configs import Mission


class TestMission:
    def test_paths(self, mission: Mission) -> None:
        assert mission.cards.is_file()
        assert mission.beacon.is_file()
        assert mission.standard.is_file()
        assert mission.common
        for key, path in mission.common.items():
            assert path.is_file()
            assert path.name.startswith(key)
        assert mission.configs
        for key, path in mission.configs.items():
            assert path.is_file()
            assert path.name.startswith(key)
        # overlays may be empty
        for key, path in mission.overlays.items():
            assert path.is_file()
            assert path.name.startswith(key)
            assert key in mission.configs
