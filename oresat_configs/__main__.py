import argparse

from . import __version__
from .scripts.gen_cand import gen_cand_files
from .scripts.gen_cand_manager import gen_cand_manager_files
from .scripts.gen_canopennode import gen_canopennode_files
from .scripts.gen_dbc import gen_dbc, gen_dbc_node
from .scripts.gen_kaitai import gen_kaitai
from .scripts.gen_xtce import gen_xtce


def main():
    parser = argparse.ArgumentParser(prog="oresat_configs")
    parser.add_argument("--version", action="version", version="%(prog)s v" + __version__)

    subparsers = parser.add_subparsers(dest="subcommand")

    subparser = subparsers.add_parser("cand", help="generate files for an cand project")
    subparser.add_argument("od_config", help="path to od config")
    subparser.add_argument(
        "-d",
        "--dir-path",
        metavar="PATH",
        default=".",
        help="output directory path. default %(default)s",
    )

    subparser = subparsers.add_parser(
        "cand-manager", help="generate files for an manager cand project"
    )
    subparser.add_argument("cards_config", help="path to cards config")
    subparser.add_argument("mission_configs", nargs="+", help="paths to mission configs")
    subparser.add_argument(
        "-d",
        "--dir-path",
        metavar="PATH",
        default=".",
        help="output directory path. default %(default)s",
    )

    subparser = subparsers.add_parser(
        "canopennode", help="generate files for an canopennode project"
    )
    subparser.add_argument("base_od_config", help="base od config file for the node")
    subparser.add_argument(
        "common_od_config",
        nargs="?",
        default="",
        help="optional common od config file path",
    )
    subparser.add_argument(
        "-d",
        "--dir-path",
        metavar="PATH",
        default=".",
        help="output directory path. default %(default)s",
    )

    subparser = subparsers.add_parser(
        "dbc", help="generate dbc file of the full can network for savvycan"
    )
    subparser.add_argument("cards_config", help="path to cards config file")
    subparser.add_argument("mission_configs", nargs="+", help="paths to mission config(s)")

    def hex_int(node_id: str) -> int:
        return int(node_id, 16) if node_id.startswith("0x") else int(node_id)

    subparser = subparsers.add_parser("dbc_node", help="generate dbc file of a node for savvycan")
    subparser.add_argument("base_od_config", help="base od config file for the node")
    subparser.add_argument(
        "common_od_config",
        nargs="?",
        default="",
        help="optional common od config file path",
    )
    subparser.add_argument(
        "-n",
        "--node-id",
        type=hex_int,
        default="0x7C",
        help="node id for the node %(default)s",
    )

    subparser = subparsers.add_parser("kaitai", help="generate kaitai file(s) for satnogs")
    subparser.add_argument("cards_config", help="path to cards config file")
    subparser.add_argument("mission_configs", nargs="+", help="paths to mission config(s)")

    subparser = subparsers.add_parser("xtce", help="generate xtce file(s) for yamcs")
    subparser.add_argument("cards_config", help="path to cards config file")
    subparser.add_argument("mission_configs", nargs="+", help="paths to mission config(s)")

    args = parser.parse_args()

    if args.subcommand == "cand":
        gen_cand_files(args.od_config, args.dir_path)
    elif args.subcommand == "cand-manager":
        gen_cand_manager_files(args.cards_config, args.mission_configs, args.dir_path)
    elif args.subcommand == "canopennode":
        gen_canopennode_files(args.base_od_config, args.common_od_config, args.dir_path)
    elif args.subcommand == "dbc":
        gen_dbc(args.cards_config)
    elif args.subcommand == "dbc-node":
        gen_dbc_node(args.base_od_config, args.common_od_config, args.node_id)
    elif args.subcommand == "kaitai":
        gen_kaitai(args.cards_config, args.mission_configs)
    elif args.subcommand == "xtce":
        gen_xtce(args.cards_config, args.mission_configs)


if __name__ == "__main__":
    main()
