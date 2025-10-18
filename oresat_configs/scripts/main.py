"""Main entrypoint for the oresat-configs tool.

The oresat-configs tool is a collection of scrips for working with and
transforming oresat data that is meant to be shared over the various networks.
There are three categories of commands:
- Informative, which display things in a human consumable format.
- Actions, which cam be used to send or receive data from Oresat cards.
- Generators, which create machine consumable descriptions of our data in a
  variety of formats.

Process for adding a new script:
- Add as a module to this (scripts/) directory. The module must implement the
  function build_arguments() which takes the output of
  ArgumentParser.add_subparsers(). See the existing scripts for examples and
  further instructions.
- Import the module here and add it to the _SCRIPTS list.
- Test the new script out with oresat-configs <name> and be sure to add it to
  the github CI workflow.
"""

import argparse

from ..constants import __version__
from . import (
    gen_dbc,
    gen_dcf,
    gen_fw_files,
    gen_kaitai,
    gen_xtce,
    list_cards,
    pdo,
    print_od,
    sdo_transfer,
)

# TODO: Group by three categories in help:
#   - info (card, od)
#   - action (sdo, pdo)
#   - generate (dcf, xtce, fw)
# There can only be one subparsers group though, the other groupings
# would have to be done through add_argument_group() but those can't
# make subparser groups. Perhaps the packages click or pydantic-settings would
# be better?

_SCRIPTS = [
    list_cards,
    print_od,
    sdo_transfer,
    pdo,
    gen_dcf,
    gen_kaitai,
    gen_xtce,
    gen_fw_files,
    gen_dbc,
]


def oresat_configs() -> None:
    """Entry point for the top level script

    Used in pyproject.toml, for generating the oresat-configs installed script
    """
    parser = argparse.ArgumentParser(prog="oresat_configs")
    parser.add_argument("--version", action="version", version="%(prog)s v" + __version__)
    parser.set_defaults(func=lambda _: parser.print_help())
    subparsers = parser.add_subparsers(title="subcommands")

    for subcommand in _SCRIPTS:
        subcommand.build_arguments(subparsers)

    args = parser.parse_args()
    args.func(args)
