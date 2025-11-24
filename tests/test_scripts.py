from argparse import Namespace

from oresat_configs import Mission, OreSatConfig
from oresat_configs.scripts import (
    gen_dbc,
    gen_dcf,
    gen_fw_files,
    gen_kaitai,
    gen_xtce,
    list_cards,
    pdo,
    print_od,
)


class TestScripts:
    def test_dbc(self, config: OreSatConfig) -> None:
        dbc = gen_dbc.generate_dbc(config)
        assert dbc

    def test_dcf(self, config: OreSatConfig) -> None:
        for od in config.od_db.values():
            name, lines = gen_dcf.generate_dcf(od)
            assert name
            assert lines

    def test_fw_files(self, config: OreSatConfig) -> None:
        for name, od in config.od_db.items():
            odc, odh = gen_fw_files.generate_canopennode(name, od)
            assert odc
            assert odh
        odc, odh = gen_fw_files.generate_canopennode("base", config.fw_base_od)
        assert odc
        assert odh

    def test_kaitai(self, config: OreSatConfig) -> None:
        kaitai = gen_kaitai.generate_kaitai(config)
        assert kaitai

    def test_xtce(self, config: OreSatConfig) -> None:
        xtce = gen_xtce.generate_xtce(config)
        assert xtce

    def test_list_card(self, mission: Mission) -> None:
        args = Namespace()
        args.oresat = mission.arg
        list_cards.list_cards(args)

    def test_pdo(self, config: OreSatConfig) -> None:
        for od in config.od_db.values():
            pdo.listpdos(od)

    def test_print_od(self, config: OreSatConfig) -> None:
        args = Namespace()
        args.oresat = config.mission.arg
        args.verbose = True
        for name in config.od_db:
            args.card = name
            print_od.print_od(args)
