"""Entry point for for oresat_configs scripts. Invoke with either:
- python -m oresat_configs
- oresat-configs
Some scripts may be installed and run as a standalone program. Consult
pyproject.toml for names to invoke them with.

Process for adding a new script:
- Add as a module to the adjacent scripts/ directory. The module must have the
  function register_subparser() which takes the output of
  ArgumentParser.add_subparsers().
- Import the module here and add it to the _SCRIPTS list.
- If the script can also be standalone then update the pyproject.toml
  [project.scripts] section.
- Test the new script out. Remember that the script may be invoked both through
  oresat-configs and directly as a standalone.
"""

import argparse

from . import __version__
from .scripts import (
    gen_canopend,
    gen_canopennode,
    gen_dbc,
    gen_dcf,
    gen_kaitai,
    gen_xtce,
)

_SCRIPTS = [gen_dbc, gen_dcf, gen_canopend, gen_canopennode, gen_kaitai, gen_xtce]


def oresat_configs() -> None:
    """Entry point for the top level script

    Used in pyproject.toml, for generating the oresat-configs installed script
    """
    parser = argparse.ArgumentParser(prog="oresat-configs")
    parser.add_argument(
        "--version", action="version", version="%(prog)s v" + __version__
    )
    parser.set_defaults(func=lambda x: parser.print_help())
    subparsers = parser.add_subparsers(title="subcommands")

    for subcommand in _SCRIPTS:
        subcommand.register_subparser(subparsers)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    oresat_configs()
