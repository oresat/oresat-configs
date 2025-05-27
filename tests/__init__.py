"""Unit tests base for all OreSat OD databases."""

import re
import unittest

import canopen

from oresat_configs import Mission, OreSatConfig
from oresat_configs._yaml_to_od import OD_DATA_TYPES, TPDO_COMM_START, TPDO_PARA_START

INT_MIN_MAX = {
    canopen.objectdictionary.INTEGER8: (-(2**7), 2**7 - 1),
    canopen.objectdictionary.INTEGER16: (-(2**15), 2**15 - 1),
    canopen.objectdictionary.INTEGER32: (-(2**31), 2**31 - 1),
    canopen.objectdictionary.INTEGER64: (-(2**63), 2**63 - 1),
    canopen.objectdictionary.UNSIGNED8: (0, 2**8 - 1),
    canopen.objectdictionary.UNSIGNED16: (0, 2**16 - 1),
    canopen.objectdictionary.UNSIGNED32: (0, 2**32 - 1),
    canopen.objectdictionary.UNSIGNED64: (0, 2**64 - 1),
}


class TestConfig(unittest.TestCase):
    """Base class to test a OreSat OD databases."""

    def setUp(self) -> None:
        self.oresatid = Mission.ORESAT0
        self.config = OreSatConfig(self.oresatid)

    def test_tpdo_sizes(self) -> None:
        """Validate TPDO sizes."""

        for name in self.config.od_db:
            tpdos = 0
            od = self.config.od_db[name]
            for i in range(16):
                tpdo_comm_index = TPDO_COMM_START + i
                tpdo_para_index = TPDO_PARA_START + i
                has_tpdo_para = tpdo_comm_index in od
                has_tpdo_comm = tpdo_para_index in od
                self.assertEqual(has_tpdo_comm, has_tpdo_para)
                if not has_tpdo_comm and not has_tpdo_comm:
                    continue
                mapping_obj = od[tpdo_para_index]
                size = 0
                for sub in mapping_obj.subindices:
                    if sub == 0:
                        continue
                    raw = mapping_obj[sub].default
                    mapped_index = (raw & 0xFFFF0000) >> 16
                    mapped_subindex = (raw & 0x0000FF00) >> 8
                    mapped_obj = od[mapped_index]
                    if not isinstance(mapped_obj, canopen.objectdictionary.Variable):
                        mapped_obj = mapped_obj[mapped_subindex]
                    self.assertTrue(
                        mapped_obj.pdo_mappable,
                        f"{self.oresatid.name} {name} {mapped_obj.name} is not pdo mappable",
                    )
                    size += OD_DATA_TYPES[mapped_obj.data_type].size
                self.assertLessEqual(
                    size, 64, f"{self.oresatid.name} {name} TPDO{i + 1} is more than 64 bits"
                )
                tpdos += 1

            # test the number of TPDOs
            if od.device_information.product_name == "c3":
                self.assertLessEqual(tpdos, 1)
            else:
                self.assertLessEqual(tpdos, 16)

    def test_beacon(self) -> None:
        """Test all objects reference in the beacon definition exist in the C3's OD."""

        length = 0

        dynamic_len_data_types = [
            canopen.objectdictionary.VISIBLE_STRING,
            canopen.objectdictionary.OCTET_STRING,
            canopen.objectdictionary.DOMAIN,
        ]

        for obj in self.config.beacon_def:
            if obj.name == "start_chars":
                length += len(obj.default)  # start_chars is required and static
            else:
                self.assertNotIn(
                    obj.data_type,
                    dynamic_len_data_types,
                    f"{self.oresatid.name} {obj.name} is a dynamic length data type",
                )
                length += OD_DATA_TYPES[obj.data_type].size // 8  # bits to bytes

        # AX.25 payload max length = 255
        # CRC32 length = 4
        self.assertLessEqual(length, 255 - 4, f"{self.oresatid.name} beacon length too long")

    def test_record_array_length(self) -> None:
        """Test that array/record have is less than 255 objects in it."""

        for od in self.config.od_db.values():
            for index in od:
                if not isinstance(od[index], canopen.objectdictionary.Variable):
                    self.assertLessEqual(len(od[index].subindices), 255)

    def _test_snake_case(self, string: str) -> None:
        """Test that a string is snake_case."""

        regex_str = r"^[a-z][a-z0-9_]*[a-z0-9]*$"  # snake_case with no leading/trailing num or "_"
        self.assertIsNotNone(re.match(regex_str, string), f'"{string}" is not snake_case')

    def _test_variable(self, obj: canopen.objectdictionary.Variable) -> None:
        """Test that a variable is valid."""

        self.assertIsInstance(obj, canopen.objectdictionary.Variable)
        self.assertIn(obj.data_type, OD_DATA_TYPES.keys())
        self.assertIn(obj.access_type, ["ro", "wo", "rw", "rwr", "rww", "const"])
        self.assertIsInstance(obj.data_type, int)
        self._test_snake_case(obj.name)

        if not isinstance(obj.parent, canopen.ObjectDictionary):
            node_name = obj.parent.parent.device_information.product_name
        else:
            node_name = obj.parent.device_information.product_name

        # test variable's default value match the data type
        if obj.data_type == canopen.objectdictionary.BOOLEAN:
            self.assertIsInstance(
                obj.default,
                bool,
                f"{node_name} object 0x{obj.index:X} 0x{obj.subindex:02X} was not a bool",
            )
        elif obj.data_type in canopen.objectdictionary.INTEGER_TYPES:
            self.assertIsInstance(
                obj.default,
                int,
                f"{node_name} object 0x{obj.index:X} 0x{obj.subindex:02X} was not a int",
            )
            int_min, int_max = INT_MIN_MAX[obj.data_type]
            self.assertTrue(
                int_min <= obj.default <= int_max,
                f"{node_name} object 0x{obj.index:X} 0x{obj.subindex:02X} default of {obj.default}"
                f" not between {int_min} and {int_max}",
            )
        elif obj.data_type in canopen.objectdictionary.FLOAT_TYPES:
            self.assertIsInstance(
                obj.default,
                float,
                f"{node_name} object 0x{obj.index:X} 0x{obj.subindex:02X} was not a float",
            )
        elif obj.data_type == canopen.objectdictionary.VISIBLE_STRING:
            self.assertIsInstance(
                obj.default,
                str,
                f"{node_name} object 0x{obj.index:X} 0x{obj.subindex:02X} was not a str",
            )
        elif obj.data_type == canopen.objectdictionary.OCTET_STRING:
            self.assertIsInstance(
                obj.default,
                bytes,
                f"{node_name} object 0x{obj.index:X} 0x{obj.subindex:02X} was not a bytes",
            )
        elif obj.data_type == canopen.objectdictionary.DOMAIN:
            self.assertIsNone(
                obj.default, f"{node_name} object 0x{obj.index:X} 0x{obj.subindex:02X} was not None"
            )
        else:
            raise ValueError(f"unsupported data_type {obj.data_type}")

        self.assertEqual(obj.default, obj.value)

    def test_objects(self) -> None:
        """Test that all objects are valid."""

        for name, od in self.config.od_db.items():
            for index in od:
                if isinstance(od[index], canopen.objectdictionary.Variable):
                    self._test_variable(od[index])
                else:
                    self._test_snake_case(od[index].name)

                    # test subindex 0
                    self.assertIn(
                        0,
                        od[index],
                        f"{name} index 0x{index:X} is missing subindex 0x0",
                    )
                    self.assertEqual(
                        od[index][0].data_type,
                        canopen.objectdictionary.UNSIGNED8,
                        f"{name} index 0x{index:X} subindex 0x0 is not a uint8",
                    )
                    self.assertEqual(
                        od[index][0].default,
                        max(list(od[index])),
                        f"{name} index 0x{index:X} mismatch highest subindex",
                    )

                    # test all other subindexes
                    array_data_types = []
                    for subindex in od[index]:
                        if isinstance(od[index], canopen.objectdictionary.Array) and subindex != 0:
                            array_data_types.append(od[index][subindex].data_type)
                        self._test_variable(od[index][subindex])

                    # validate all array items are the same type
                    self.assertIn(len(set(array_data_types)), [0, 1])
