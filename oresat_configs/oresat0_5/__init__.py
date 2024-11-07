"""OreSat0.5 object dictionary and beacon constants."""

from importlib.resources import files

from ..base import (
    ADCS_CONFIG_PATH,
    BAT_CONFIG_PATH,
    C3_CONFIG_PATH,
    CFC_CONFIG_PATH,
    DIODE_CONFIG_PATH,
    DXWIFI_CONFIG_PATH,
    FW_COMMON_CONFIG_PATH,
    GPS_CONFIG_PATH,
    RW_CONFIG_PATH,
    SOLAR_CONFIG_PATH,
    ST_CONFIG_PATH,
    SW_COMMON_CONFIG_PATH,
    ConfigPaths,
)

_CONFIGS_DIR = files(__name__)
BEACON_CONFIG_PATH = _CONFIGS_DIR / "beacon.yaml"
CARDS_CSV_PATH = _CONFIGS_DIR / "cards.csv"

CARD_CONFIGS_PATH: ConfigPaths = {
    "c3": (C3_CONFIG_PATH, SW_COMMON_CONFIG_PATH),
    "battery_1": (BAT_CONFIG_PATH, FW_COMMON_CONFIG_PATH),
    "solar_1": (SOLAR_CONFIG_PATH, FW_COMMON_CONFIG_PATH),
    "solar_2": (SOLAR_CONFIG_PATH, FW_COMMON_CONFIG_PATH),
    "solar_3": (SOLAR_CONFIG_PATH, FW_COMMON_CONFIG_PATH),
    "solar_4": (SOLAR_CONFIG_PATH, FW_COMMON_CONFIG_PATH),
    "solar_5": (SOLAR_CONFIG_PATH, FW_COMMON_CONFIG_PATH),
    "solar_6": (SOLAR_CONFIG_PATH, FW_COMMON_CONFIG_PATH),
    "adcs": (ADCS_CONFIG_PATH, FW_COMMON_CONFIG_PATH),
    "rw_1": (RW_CONFIG_PATH, FW_COMMON_CONFIG_PATH),
    "rw_2": (RW_CONFIG_PATH, FW_COMMON_CONFIG_PATH),
    "rw_3": (RW_CONFIG_PATH, FW_COMMON_CONFIG_PATH),
    "rw_4": (RW_CONFIG_PATH, FW_COMMON_CONFIG_PATH),
    "gps": (GPS_CONFIG_PATH, SW_COMMON_CONFIG_PATH),
    "star_tracker_1": (ST_CONFIG_PATH, SW_COMMON_CONFIG_PATH),
    "dxwifi": (DXWIFI_CONFIG_PATH, SW_COMMON_CONFIG_PATH),
    "cfc_processor": (CFC_CONFIG_PATH, SW_COMMON_CONFIG_PATH),
    "cfc_sensor": None,
    "diode_test": (DIODE_CONFIG_PATH, FW_COMMON_CONFIG_PATH),
}
