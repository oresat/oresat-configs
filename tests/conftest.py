import pytest

from oresat_configs import Mission, OreSatConfig


@pytest.fixture(params=list(Mission))
def mission(request: pytest.FixtureRequest) -> Mission:
    return request.param


@pytest.fixture
def config(mission: Mission) -> OreSatConfig:
    return OreSatConfig(mission)
