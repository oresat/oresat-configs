try:
    from .._version import version as __version__  # type: ignore
except ImportError:
    __version__ = "0.0.0"  # package is not installed


INDENT3 = " " * 3
INDENT4 = " " * 4
INDENT8 = " " * 8
INDENT12 = " " * 12
INDENT16 = " " * 16


def snake_to_camel(name):
    return "".join(word.title() for word in name.split("_"))
