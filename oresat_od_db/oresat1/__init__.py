"""OreSat1 object dictionary and beacon globals."""

import os

import yaml

from .. import NodeId, OreSatId
from .._yaml_to_od import gen_od_db, read_yaml_od_config
from ..base import (
    BAT_CONFIG,
    C3_CONFIG,
    CFC_CONFIG,
    DXWIFI_CONFIG,
    FW_COMMON_CONFIG,
    GPS_CONFIG,
    IMU_CONFIG,
    RW_CONFIG,
    SOLAR_CONFIG,
    ST_CONFIG,
    SW_COMMON_CONFIG,
)

_CONFIGS_DIR = f"{os.path.dirname(os.path.abspath(__file__))}/configs"

with open(f"{_CONFIGS_DIR}/beacon.yaml", "r") as f:
    ORESAT1_BEACON_DEF = yaml.safe_load(f)


ORESAT1_OD_DB = gen_od_db(
    OreSatId.ORESAT1,
    ORESAT1_BEACON_DEF,
    {
        NodeId.C3: (C3_CONFIG, SW_COMMON_CONFIG),
        NodeId.BATTERY_1: (BAT_CONFIG, FW_COMMON_CONFIG),
        NodeId.BATTERY_2: (BAT_CONFIG, FW_COMMON_CONFIG),
        NodeId.SOLAR_MODULE_1: (SOLAR_CONFIG, FW_COMMON_CONFIG),
        NodeId.SOLAR_MODULE_2: (SOLAR_CONFIG, FW_COMMON_CONFIG),
        NodeId.SOLAR_MODULE_3: (SOLAR_CONFIG, FW_COMMON_CONFIG),
        NodeId.SOLAR_MODULE_4: (SOLAR_CONFIG, FW_COMMON_CONFIG),
        NodeId.SOLAR_MODULE_5: (SOLAR_CONFIG, FW_COMMON_CONFIG),
        NodeId.SOLAR_MODULE_6: (SOLAR_CONFIG, FW_COMMON_CONFIG),
        NodeId.SOLAR_MODULE_7: (SOLAR_CONFIG, FW_COMMON_CONFIG),
        NodeId.SOLAR_MODULE_8: (SOLAR_CONFIG, FW_COMMON_CONFIG),
        NodeId.IMU: (IMU_CONFIG, FW_COMMON_CONFIG),
        NodeId.REACTION_WHEEL_1: (RW_CONFIG, FW_COMMON_CONFIG),
        NodeId.REACTION_WHEEL_2: (RW_CONFIG, FW_COMMON_CONFIG),
        NodeId.REACTION_WHEEL_3: (RW_CONFIG, FW_COMMON_CONFIG),
        NodeId.REACTION_WHEEL_4: (RW_CONFIG, FW_COMMON_CONFIG),
        NodeId.GPS: (GPS_CONFIG, SW_COMMON_CONFIG),
        NodeId.STAR_TRACKER_1: (ST_CONFIG, SW_COMMON_CONFIG),
        NodeId.STAR_TRACKER_2: (ST_CONFIG, SW_COMMON_CONFIG),
        NodeId.DXWIFI: (DXWIFI_CONFIG, SW_COMMON_CONFIG),
        NodeId.CFC: (CFC_CONFIG, SW_COMMON_CONFIG),
    },
)

# direct access to ODs
ORESAT1_C3_OD = ORESAT1_OD_DB[NodeId.C3]
ORESAT1_BATTERY_1_OD = ORESAT1_OD_DB[NodeId.BATTERY_1]
ORESAT1_BATTERY_2_OD = ORESAT1_OD_DB[NodeId.BATTERY_2]
ORESAT1_SOLAR_MODULE_1_OD = ORESAT1_OD_DB[NodeId.SOLAR_MODULE_1]
ORESAT1_SOLAR_MODULE_2_OD = ORESAT1_OD_DB[NodeId.SOLAR_MODULE_2]
ORESAT1_SOLAR_MODULE_3_OD = ORESAT1_OD_DB[NodeId.SOLAR_MODULE_3]
ORESAT1_SOLAR_MODULE_4_OD = ORESAT1_OD_DB[NodeId.SOLAR_MODULE_4]
ORESAT1_SOLAR_MODULE_5_OD = ORESAT1_OD_DB[NodeId.SOLAR_MODULE_5]
ORESAT1_SOLAR_MODULE_6_OD = ORESAT1_OD_DB[NodeId.SOLAR_MODULE_6]
ORESAT1_SOLAR_MODULE_7_OD = ORESAT1_OD_DB[NodeId.SOLAR_MODULE_7]
ORESAT1_SOLAR_MODULE_8_OD = ORESAT1_OD_DB[NodeId.SOLAR_MODULE_8]
ORESAT1_IMU_OD = ORESAT1_OD_DB[NodeId.IMU]
ORESAT1_REACTION_WHEEL_1_OD = ORESAT1_OD_DB[NodeId.REACTION_WHEEL_1]
ORESAT1_REACTION_WHEEL_2_OD = ORESAT1_OD_DB[NodeId.REACTION_WHEEL_2]
ORESAT1_REACTION_WHEEL_3_OD = ORESAT1_OD_DB[NodeId.REACTION_WHEEL_3]
ORESAT1_REACTION_WHEEL_4_OD = ORESAT1_OD_DB[NodeId.REACTION_WHEEL_4]
ORESAT1_GPS_OD = ORESAT1_OD_DB[NodeId.GPS]
ORESAT1_STAR_TRACKER_1_OD = ORESAT1_OD_DB[NodeId.STAR_TRACKER_1]
ORESAT1_STAR_TRACKER_2_OD = ORESAT1_OD_DB[NodeId.STAR_TRACKER_2]
ORESAT1_DXWIFI_OD = ORESAT1_OD_DB[NodeId.DXWIFI]
ORESAT1_CFC_OD = ORESAT1_OD_DB[NodeId.CFC]
