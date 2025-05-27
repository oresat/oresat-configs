"""Unit tests for OreSat0 OD database."""

from oresat_configs import Mission, OreSatConfig

from . import TestConfig


class TestOreSat0(TestConfig):
    """Test the OreSat0 OD database."""

    def setUp(self) -> None:
        self.oresatid = Mission.ORESAT0
        self.config = OreSatConfig(self.oresatid)
