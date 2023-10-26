"""OreSat0 object dictionary and beacon constants."""

import os

import yaml

from .._yaml_to_od import (
    gen_fw_base_od,
    gen_od_db,
    get_c3_beacon_defs,
    get_c3_fram_defs,
    read_yaml_od_config,
)
from ..base import (
    BAT_CONFIG,
    C3_CONFIG,
    DXWIFI_CONFIG,
    FW_COMMON_CONFIG,
    GPS_CONFIG,
    IMU_CONFIG,
    SOLAR_CONFIG,
    ST_CONFIG,
    SW_COMMON_CONFIG,
)
from ..constants import NodeId, OreSatId

_CONFIGS_DIR = os.path.dirname(os.path.abspath(__file__))
C3_CONFIG_OVERLAY = read_yaml_od_config(f"{_CONFIGS_DIR}/c3_overlay.yaml")
BAT_CONFIG_OVERLAY = read_yaml_od_config(f"{_CONFIGS_DIR}/battery_overlay.yaml")

with open(f"{_CONFIGS_DIR}/beacon.yaml", "r") as f:
    ORESAT0_BEACON_CONFIG = yaml.safe_load(f)

ORESAT0_OD_DB = gen_od_db(
    OreSatId.ORESAT0,
    ORESAT0_BEACON_CONFIG,
    {
        NodeId.C3: (C3_CONFIG, FW_COMMON_CONFIG, C3_CONFIG_OVERLAY),
        NodeId.BATTERY_1: (BAT_CONFIG, FW_COMMON_CONFIG, BAT_CONFIG_OVERLAY),
        NodeId.SOLAR_MODULE_1: (SOLAR_CONFIG, FW_COMMON_CONFIG),
        NodeId.SOLAR_MODULE_2: (SOLAR_CONFIG, FW_COMMON_CONFIG),
        NodeId.SOLAR_MODULE_3: (SOLAR_CONFIG, FW_COMMON_CONFIG),
        NodeId.SOLAR_MODULE_4: (SOLAR_CONFIG, FW_COMMON_CONFIG),
        NodeId.IMU: (IMU_CONFIG, FW_COMMON_CONFIG),
        NodeId.GPS: (GPS_CONFIG, SW_COMMON_CONFIG),
        NodeId.STAR_TRACKER_1: (ST_CONFIG, SW_COMMON_CONFIG),
        NodeId.DXWIFI: (DXWIFI_CONFIG, SW_COMMON_CONFIG),
    },
)

# direct access to ODs
ORESAT0_C3_OD = ORESAT0_OD_DB[NodeId.C3]
ORESAT0_BATTERY_1_OD = ORESAT0_OD_DB[NodeId.BATTERY_1]
ORESAT0_SOLAR_MODULE_1_OD = ORESAT0_OD_DB[NodeId.SOLAR_MODULE_1]
ORESAT0_SOLAR_MODULE_2_OD = ORESAT0_OD_DB[NodeId.SOLAR_MODULE_2]
ORESAT0_SOLAR_MODULE_3_OD = ORESAT0_OD_DB[NodeId.SOLAR_MODULE_3]
ORESAT0_SOLAR_MODULE_4_OD = ORESAT0_OD_DB[NodeId.SOLAR_MODULE_4]
ORESAT0_IMU_OD = ORESAT0_OD_DB[NodeId.IMU]
ORESAT0_GPS_OD = ORESAT0_OD_DB[NodeId.GPS]
ORESAT0_STAR_TRACKER_1_OD = ORESAT0_OD_DB[NodeId.STAR_TRACKER_1]
ORESAT0_DXWIFI_OD = ORESAT0_OD_DB[NodeId.DXWIFI]

ORESAT0_BEACON_DEF = get_c3_beacon_defs(ORESAT0_C3_OD, ORESAT0_BEACON_CONFIG)
ORESAT0_FRAM_DEF = get_c3_fram_defs(ORESAT0_C3_OD, C3_CONFIG)

ORESAT0_FW_BASE_OD = gen_fw_base_od(OreSatId.ORESAT0, FW_COMMON_CONFIG)