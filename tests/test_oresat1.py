"""Unit tests for OreSat1 OD database."""

from oresat_configs import Mission, OreSatConfig

from . import TestConfig


class TestOreSat1(TestConfig):
    """Test the OreSat1 OD database"""

    def setUp(self) -> None:
        self.oresatid = Mission.ORESAT1
        self.config = OreSatConfig(self.oresatid)
