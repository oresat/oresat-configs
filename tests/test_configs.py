"""Unit tests base for all OreSat OD databases."""

import re

import canopen
from canopen.objectdictionary import Array, Record

from oresat_configs import OreSatConfig
from oresat_configs.card_config import DATA_TYPE_DEFAULTS
from oresat_configs.odtypes import PDOCommunicationParameter, PDOMappingParameter

OD_TYPE_DEFAULTS = {default.od_type: default for default in DATA_TYPE_DEFAULTS.values()}


class TestConfig:
    """Base class to test a OreSat OD databases."""

    def test_tpdo_sizes(self, config: OreSatConfig) -> None:
        """Validate TPDO sizes."""

        for name, od in config.od_db.items():
            tpdos = 0
            for i in range(16):
                tpdo_comm_index = PDOCommunicationParameter.INDEX_BASE['tpdo'] + i
                tpdo_para_index = PDOMappingParameter.INDEX_BASE['tpdo'] + i
                has_tpdo_para = tpdo_comm_index in od
                has_tpdo_comm = tpdo_para_index in od
                assert has_tpdo_comm == has_tpdo_para
                if not has_tpdo_comm and not has_tpdo_comm:
                    continue
                mapping_obj = od[tpdo_para_index]
                assert isinstance(mapping_obj, Record)
                size = 0
                for sub in mapping_obj.subindices:
                    if sub == 0:
                        continue
                    default = mapping_obj[sub].default
                    assert default is not None
                    mapped_index = (default & 0xFFFF0000) >> 16
                    mapped_subindex = (default & 0x0000FF00) >> 8
                    mapped_obj = od[mapped_index]
                    if not isinstance(mapped_obj, canopen.objectdictionary.Variable):
                        mapped_obj = mapped_obj[mapped_subindex]
                    assert mapped_obj.pdo_mappable, (
                        f"{config.mission} {name} {mapped_obj.name} is not pdo mappable"
                    )
                    assert mapped_obj.data_type is not None
                    size += OD_TYPE_DEFAULTS[mapped_obj.data_type].size
                assert size <= 64, f"{config.mission} {name} TPDO{i + 1} is more than 64 bits"
                tpdos += 1

            # test the number of TPDOs
            if od.device_information.product_name == "c3":
                assert tpdos <= 1
            else:
                assert tpdos <= 16

    def test_beacon(self, config: OreSatConfig) -> None:
        """Test all objects reference in the beacon definition exist in the C3's OD."""

        length = 0

        dynamic_len_data_types = [
            canopen.objectdictionary.VISIBLE_STRING,
            canopen.objectdictionary.OCTET_STRING,
            canopen.objectdictionary.DOMAIN,
        ]

        for obj in config.beacon_def:
            if obj.name == "start_chars":
                assert isinstance(obj.default, str)
                length += len(obj.default)  # start_chars is required and static
            else:
                assert obj.data_type is not None
                assert obj.data_type not in dynamic_len_data_types, (
                    f"{config.mission} {obj.name} is a dynamic length data type"
                )
                length += OD_TYPE_DEFAULTS[obj.data_type].size // 8  # bits to bytes

        # AX.25 payload max length = 255
        # CRC32 length = 4
        assert length <= 255 - 4, f"{config.mission} beacon length too long"

    def test_record_array_length(self, config: OreSatConfig) -> None:
        """Test that array/record have is less than 255 objects in it."""

        for od in config.od_db.values():
            for entry in od.values():
                if not isinstance(entry, canopen.objectdictionary.Variable):
                    assert len(entry.subindices) <= 255

    def _test_snake_case(self, string: str) -> None:
        """Test that a string is snake_case."""

        regex_str = r"^[a-z][a-z0-9_]*[a-z0-9]*$"  # snake_case with no leading/trailing num or "_"
        assert re.match(regex_str, string) is not None, f'"{string}" is not snake_case'

    def _test_variable(self, obj: canopen.objectdictionary.Variable) -> None:
        """Test that a variable is valid."""

        assert isinstance(obj, canopen.objectdictionary.Variable)
        assert obj.data_type in OD_TYPE_DEFAULTS
        assert obj.access_type in ["ro", "wo", "rw", "rwr", "rww", "const"]
        assert isinstance(obj.data_type, int)
        self._test_snake_case(obj.name)

        assert obj.parent is not None
        if isinstance(obj.parent, (Array, Record)):
            node_name = obj.parent.parent.device_information.product_name
        else:
            node_name = obj.parent.device_information.product_name

        # test variable's default value match the data type
        if obj.data_type == canopen.objectdictionary.BOOLEAN:
            assert isinstance(obj.default, bool), (
                f"{node_name} object 0x{obj.index:X} 0x{obj.subindex:02X} was not a bool"
            )
        elif obj.data_type in canopen.objectdictionary.INTEGER_TYPES:
            assert isinstance(obj.default, int), (
                f"{node_name} object 0x{obj.index:X} 0x{obj.subindex:02X} was not a int"
            )
            int_min = OD_TYPE_DEFAULTS[obj.data_type].low_limit
            int_max = OD_TYPE_DEFAULTS[obj.data_type].high_limit
            assert int_min <= obj.default <= int_max, (
                f"{node_name} object 0x{obj.index:X} 0x{obj.subindex:02X} default of {obj.default}"
                f"not between {int_min} and {int_max}"
            )
        elif obj.data_type in canopen.objectdictionary.FLOAT_TYPES:
            assert isinstance(obj.default, float), (
                f"{node_name} object 0x{obj.index:X} 0x{obj.subindex:02X} was not a float"
            )
        elif obj.data_type == canopen.objectdictionary.VISIBLE_STRING:
            assert isinstance(obj.default, str), (
                f"{node_name} object 0x{obj.index:X} 0x{obj.subindex:02X} was not a str"
            )
        elif obj.data_type == canopen.objectdictionary.OCTET_STRING:
            assert isinstance(obj.default, bytes), (
                f"{node_name} object 0x{obj.index:X} 0x{obj.subindex:02X} was not a bytes"
            )
        elif obj.data_type == canopen.objectdictionary.DOMAIN:
            assert obj.default is None, (
                f"{node_name} object 0x{obj.index:X} 0x{obj.subindex:02X} was not None"
            )
        else:
            raise ValueError(f"unsupported data_type {obj.data_type}")

        assert obj.default == obj.value

    def test_objects(self, config: OreSatConfig) -> None:
        """Test that all objects are valid."""

        for name, od in config.od_db.items():
            for index, entry in od.items():
                if isinstance(entry, canopen.objectdictionary.Variable):
                    self._test_variable(entry)
                else:
                    self._test_snake_case(entry.name)

                    # test subindex 0
                    assert 0 in entry, f"{name} index 0x{index:X} is missing subindex 0x0"
                    assert entry[0].data_type == canopen.objectdictionary.UNSIGNED8, (
                        f"{name} index 0x{index:X} subindex 0x0 is not a uint8"
                    )
                    assert entry[0].default == max(list(entry)), (
                        f"{name} index 0x{index:X} mismatch highest subindex"
                    )

                    # test all other subindexes
                    array_data_types = []
                    for subindex, subentry in entry.items():
                        if isinstance(entry, canopen.objectdictionary.Array) and subindex != 0:
                            array_data_types.append(subentry.data_type)
                        self._test_variable(subentry)

                    # validate all array items are the same type
                    assert len(set(array_data_types)) in [0, 1]
