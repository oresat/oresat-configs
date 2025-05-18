try:
    from .._version import version as __version__
except ImportError:
    __version__ = "0.0.0"  # package is not installed


INDENT3 = " " * 3
INDENT4 = " " * 4
INDENT8 = " " * 8
INDENT12 = " " * 12
INDENT16 = " " * 16

CANOPEN_STD_OBJS_START = 0x1000
OTHER_STD_OBJS_START = 0x2000
BASE_OBJS_START = 0x3000
APP_OBJS_START = 0x4000
RPDO_OBJS_START = 0x5000


def snake_to_camel(name: str) -> str:
    return "".join(word.title() for word in name.split("_"))
