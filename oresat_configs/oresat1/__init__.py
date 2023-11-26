"""OreSat1 object dictionary and beacon constants."""

import os

from ..base import (
    BAT_CONFIG_PATH,
    C3_CONFIG_PATH,
    CFC_CONFIG_PATH,
    DXWIFI_CONFIG_PATH,
    FW_COMMON_CONFIG_PATH,
    GPS_CONFIG_PATH,
    IMU_CONFIG_PATH,
    RW_CONFIG_PATH,
    SOLAR_CONFIG_PATH,
    ST_CONFIG_PATH,
    SW_COMMON_CONFIG_PATH,
)
from ..constants import NodeId

_CONFIGS_DIR = os.path.dirname(os.path.abspath(__file__))

ORESAT1_BEACON_CONFIG_PATH = f"{_CONFIGS_DIR}/beacon.yaml"

ORESAT1_CARD_CONFIGS_PATH = {
    NodeId.C3: (C3_CONFIG_PATH, SW_COMMON_CONFIG_PATH),
    NodeId.BATTERY_1: (BAT_CONFIG_PATH, FW_COMMON_CONFIG_PATH),
    NodeId.BATTERY_2: (BAT_CONFIG_PATH, FW_COMMON_CONFIG_PATH),
    NodeId.SOLAR_MODULE_1: (SOLAR_CONFIG_PATH, FW_COMMON_CONFIG_PATH),
    NodeId.SOLAR_MODULE_2: (SOLAR_CONFIG_PATH, FW_COMMON_CONFIG_PATH),
    NodeId.SOLAR_MODULE_3: (SOLAR_CONFIG_PATH, FW_COMMON_CONFIG_PATH),
    NodeId.SOLAR_MODULE_4: (SOLAR_CONFIG_PATH, FW_COMMON_CONFIG_PATH),
    NodeId.SOLAR_MODULE_5: (SOLAR_CONFIG_PATH, FW_COMMON_CONFIG_PATH),
    NodeId.SOLAR_MODULE_6: (SOLAR_CONFIG_PATH, FW_COMMON_CONFIG_PATH),
    NodeId.SOLAR_MODULE_7: (SOLAR_CONFIG_PATH, FW_COMMON_CONFIG_PATH),
    NodeId.SOLAR_MODULE_8: (SOLAR_CONFIG_PATH, FW_COMMON_CONFIG_PATH),
    NodeId.IMU: (IMU_CONFIG_PATH, FW_COMMON_CONFIG_PATH),
    NodeId.REACTION_WHEEL_1: (RW_CONFIG_PATH, FW_COMMON_CONFIG_PATH),
    NodeId.REACTION_WHEEL_2: (RW_CONFIG_PATH, FW_COMMON_CONFIG_PATH),
    NodeId.REACTION_WHEEL_3: (RW_CONFIG_PATH, FW_COMMON_CONFIG_PATH),
    NodeId.REACTION_WHEEL_4: (RW_CONFIG_PATH, FW_COMMON_CONFIG_PATH),
    NodeId.GPS: (GPS_CONFIG_PATH, SW_COMMON_CONFIG_PATH),
    NodeId.STAR_TRACKER_1: (ST_CONFIG_PATH, SW_COMMON_CONFIG_PATH),
    NodeId.STAR_TRACKER_2: (ST_CONFIG_PATH, SW_COMMON_CONFIG_PATH),
    NodeId.DXWIFI: (DXWIFI_CONFIG_PATH, SW_COMMON_CONFIG_PATH),
    NodeId.CFC: (CFC_CONFIG_PATH, SW_COMMON_CONFIG_PATH),
}
