from oresat_configs import Mission
from oresat_configs.card_info import cards_from_csv


class TestCard:
    def test_basename(self, mission: Mission) -> None:
        for name, card in cards_from_csv(mission.cards).items():
            basename = card.basename
            if basename == 'reaction_wheel':
                basename = 'rw'
            assert name.startswith(basename)

    def test_basetype(self, mission: Mission) -> None:
        for card in cards_from_csv(mission.cards).values():
            assert card.basetype in ('fw', 'sw', None)
