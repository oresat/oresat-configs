"""Generate XTCE for the beacon."""

import xml.etree.ElementTree as ET
from argparse import ArgumentParser, Namespace
from datetime import datetime
from typing import Any, Optional

import canopen

from .. import Mission, OreSatConfig

GEN_XTCE = "generate beacon xtce file"


def build_parser(parser: ArgumentParser) -> ArgumentParser:
    """Configures an ArgumentParser suitable for this script.

    The given parser may be standalone or it may be used as a subcommand in another ArgumentParser.
    """
    parser.description = GEN_XTCE
    parser.add_argument(
        "--oresat",
        default=Mission.default().arg,
        choices=[m.arg for m in Mission],
        type=lambda x: x.lower().removeprefix("oresat"),
        help="Oresat Mission. (Default: %(default)s)",
    )
    parser.add_argument(
        "-d", "--dir-path", default=".", help="Output directory path. (Default: %(default)s)"
    )
    return parser


def register_subparser(subparsers: Any) -> None:
    """Registers an ArgumentParser as a subcommand of another parser.

    Intended to be called by __main__.py for each script. Given the output of add_subparsers(),
    (which I think is a subparser group, but is technically unspecified) this function should
    create its own ArgumentParser via add_parser(). It must also set_default() the func argument
    to designate the entry point into this script.
    See https://docs.python.org/3/library/argparse.html#sub-commands, especially the end of that
    section, for more.
    """
    parser = build_parser(subparsers.add_parser("xtce", help=GEN_XTCE))
    parser.set_defaults(func=gen_xtce)


CANOPEN_TO_XTCE_DT = {
    canopen.objectdictionary.BOOLEAN: "bool",
    canopen.objectdictionary.INTEGER8: "int8",
    canopen.objectdictionary.INTEGER16: "int16",
    canopen.objectdictionary.INTEGER32: "int32",
    canopen.objectdictionary.INTEGER64: "int64",
    canopen.objectdictionary.UNSIGNED8: "uint8",
    canopen.objectdictionary.UNSIGNED16: "uint16",
    canopen.objectdictionary.UNSIGNED32: "uint32",
    canopen.objectdictionary.UNSIGNED64: "uint64",
    canopen.objectdictionary.VISIBLE_STRING: "string",
    canopen.objectdictionary.REAL32: "float",
    canopen.objectdictionary.REAL64: "double",
}

DT_LEN = {
    canopen.objectdictionary.BOOLEAN: 8,
    canopen.objectdictionary.INTEGER8: 8,
    canopen.objectdictionary.INTEGER16: 16,
    canopen.objectdictionary.INTEGER32: 32,
    canopen.objectdictionary.INTEGER64: 64,
    canopen.objectdictionary.UNSIGNED8: 8,
    canopen.objectdictionary.UNSIGNED16: 16,
    canopen.objectdictionary.UNSIGNED32: 32,
    canopen.objectdictionary.UNSIGNED64: 64,
    canopen.objectdictionary.VISIBLE_STRING: 0,
    canopen.objectdictionary.REAL32: 32,
    canopen.objectdictionary.REAL64: 64,
}


def make_obj_name(obj: canopen.objectdictionary.Variable) -> str:
    """get obj name."""

    name = ""
    if obj.index < 0x5000:
        name += "c3_"

    if isinstance(obj.parent, canopen.ObjectDictionary):
        name += obj.name
    else:
        name += f"{obj.parent.name}_{obj.name}"

    return name


def make_dt_name(obj: canopen.objectdictionary.Variable) -> str:
    """Make xtce data type name."""

    type_name = CANOPEN_TO_XTCE_DT[obj.data_type]
    if obj.name in ["unix_time", "updater_status"]:
        type_name = obj.name
    elif obj.value_descriptions:
        if isinstance(obj.parent, canopen.ObjectDictionary):
            type_name += f"_c3_{obj.name}"
        else:
            type_name += f"_{obj.parent.name}_{obj.name}"
    elif obj.data_type == canopen.objectdictionary.VISIBLE_STRING:
        type_name += f"{len(obj.default) * 8}"
    elif obj.unit:
        type_name += f"_{obj.unit}"
    type_name = type_name.replace("/", "p").replace("%", "percent")

    type_name += "_type"

    return type_name


def write_xtce(config: OreSatConfig, dir_path: str = ".") -> None:
    """Write beacon configs to a xtce file."""

    root = ET.Element(
        "SpaceSystem",
        attrib={
            "name": config.mission.filename(),
            "xmlns": "http://www.omg.org/spec/XTCE/20180204",
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xsi:schemaLocation": (
                "http://www.omg.org/spec/XTCE/20180204 "
                "https://www.omg.org/spec/XTCE/20180204/SpaceSystem.xsd"
            ),
        },
    )

    header = ET.SubElement(
        root,
        "Header",
        attrib={
            "validationStatus": "Working",
            "classification": "NotClassified",
            "version": f'{config.od_db["c3"]["beacon"]["revision"].value}.0',
            "date": datetime.now().strftime("%Y-%m-%d"),
        },
    )
    author_set = ET.SubElement(header, "AuthorSet")
    author = ET.SubElement(author_set, "Author")
    author.text = "PSAS (Portland State Aerospace Society)"

    tm_meta = ET.SubElement(root, "TelemetryMetaData")
    tm_meta_para = ET.SubElement(tm_meta, "ParameterTypeSet")

    # hard-code the unitless uint32 type for the crc32
    uint32_type = ET.SubElement(
        tm_meta_para,
        "IntegerParameterType",
        attrib={
            "name": "uint32_type",
        },
    )
    ET.SubElement(uint32_type, "UnitSet")
    bin_data_enc = ET.SubElement(
        uint32_type,
        "IntegerDataEncoding",
        attrib={
            "bitOrder": "leastSignificantBitFirst",
            "encoding": "unsigned",
            "sizeInBits": "32",
        },
    )

    # hard-code the 128b type for the AX.25 parameter
    uint128_type = ET.SubElement(
        tm_meta_para,
        "BinaryParameterType",
        attrib={
            "name": "b128_type",
            "shortDescription": "128 bitfield",
        },
    )
    ET.SubElement(uint128_type, "UnitSet")
    bin_data_enc = ET.SubElement(
        uint128_type, "BinaryDataEncoding", attrib={"bitOrder": "leastSignificantBitFirst"}
    )
    bin_data_enc_size = ET.SubElement(
        bin_data_enc,
        "SizeInBits",
    )
    bin_data_enc_size_fixed = ET.SubElement(
        bin_data_enc_size,
        "FixedValue",
    )
    bin_data_enc_size_fixed.text = "128"

    # hard-code the unix time type
    para_type = ET.SubElement(
        tm_meta_para,
        "AbsoluteTimeParameterType",
        attrib={
            "name": "unix_time",
            "shortDescription": "Unix coarse timestamp",
        },
    )
    enc = ET.SubElement(para_type, "Encoding")
    ET.SubElement(
        enc,
        "IntegerDataEncoding",
        attrib={
            "byteOrder": "leastSignificantByteFirst",
            "sizeInBits": "32",
        },
    )
    ref_time = ET.SubElement(para_type, "ReferenceTime")
    epoch = ET.SubElement(ref_time, "Epoch")
    epoch.text = "1970-01-01T00:00:00.000"

    para_types = ["unix_time", "b128_type", "uint32_type"]
    for obj in config.beacon_def:
        name = make_dt_name(obj)
        if name in para_types:
            continue
        para_types.append(name)

        if obj.data_type == canopen.objectdictionary.BOOLEAN:
            para_type = ET.SubElement(
                tm_meta_para,
                "BooleanParameterType",
                attrib={
                    "name": name,
                    "zeroStringValue": "0",
                    "oneStringValue": "1",
                },
            )
        elif obj.data_type in canopen.objectdictionary.UNSIGNED_TYPES and obj.value_descriptions:
            para_type = ET.SubElement(
                tm_meta_para,
                "EnumeratedParameterType",
                attrib={
                    "name": name,
                },
            )
            enum_list = ET.SubElement(para_type, "EnumerationList")
            for value, name in obj.value_descriptions.items():
                ET.SubElement(
                    enum_list,
                    "Enumeration",
                    attrib={
                        "value": str(value),
                        "label": name,
                    },
                )
        elif obj.data_type in canopen.objectdictionary.INTEGER_TYPES:
            if obj.data_type in canopen.objectdictionary.UNSIGNED_TYPES:
                signed = False
                encoding = "unsigned"
            else:
                signed = True
                encoding = "twosComplement"

            para_type = ET.SubElement(
                tm_meta_para,
                "IntegerParameterType",
                attrib={
                    "name": name,
                    "signed": str(signed).lower(),
                },
            )

            para_unit_set = ET.SubElement(para_type, "UnitSet")
            if obj.unit:
                para_unit = ET.SubElement(
                    para_unit_set,
                    "Unit",
                    attrib={
                        "description": obj.unit,
                    },
                )
                para_unit.text = obj.unit

            data_enc = ET.SubElement(
                para_type,
                "IntegerDataEncoding",
                attrib={
                    "byteOrder": "leastSignificantByteFirst",
                    "encoding": encoding,
                    "sizeInBits": str(DT_LEN[obj.data_type]),
                },
            )
            if obj.factor != 1:
                def_cal = ET.SubElement(data_enc, "DefaultCalibrator")
                poly_cal = ET.SubElement(def_cal, "PolynomialCalibrator")
                ET.SubElement(
                    poly_cal,
                    "Term",
                    attrib={
                        "exponent": "1",
                        "coefficient": str(obj.factor),
                    },
                )
        elif obj.data_type == canopen.objectdictionary.VISIBLE_STRING:
            para_type = ET.SubElement(
                tm_meta_para,
                "StringParameterType",
                attrib={
                    "name": name,
                },
            )
            str_para_type = ET.SubElement(
                para_type,
                "StringDataEncoding",
                attrib={
                    "encoding": "UTF-8",
                },
            )
            size_in_bits = ET.SubElement(str_para_type, "SizeInBits")
            fixed = ET.SubElement(size_in_bits, "Fixed")
            fixed_value = ET.SubElement(fixed, "FixedValue")
            fixed_value.text = str(len(obj.default) * 8)

    para_set = ET.SubElement(tm_meta, "ParameterSet")

    # hard-code the AX.25 headers as a Binary128 type
    ET.SubElement(
        para_set,
        "Parameter",
        attrib={
            "name": "ax25_header",
            "parameterTypeRef": "b128_type",
            "shortDescription": "AX.25 Header",
        },
    )
    for obj in config.beacon_def:
        ET.SubElement(
            para_set,
            "Parameter",
            attrib={
                "name": make_obj_name(obj),
                "parameterTypeRef": make_dt_name(obj),
                "shortDescription": obj.description,
            },
        )
    ET.SubElement(
        para_set,
        "Parameter",
        attrib={
            "name": "crc32",
            "parameterTypeRef": "uint32_type",
            "shortDescription": "crc check for beacon",
        },
    )

    cont_set = ET.SubElement(tm_meta, "ContainerSet")
    seq_cont = ET.SubElement(
        cont_set,
        "SequenceContainer",
        attrib={
            "name": "Beacon",
        },
    )
    entry_list = ET.SubElement(seq_cont, "EntryList")
    ET.SubElement(
        entry_list,
        "ParameterRefEntry",
        attrib={"parameterRef": "ax25_header"},
    )
    for obj in config.beacon_def:
        ET.SubElement(
            entry_list,
            "ParameterRefEntry",
            attrib={
                "parameterRef": make_obj_name(obj),
            },
        )
    ET.SubElement(
        entry_list,
        "ParameterRefEntry",
        attrib={
            "parameterRef": "crc32",
        },
    )

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ", level=0)
    file_name = f"{config.mission.filename()}.xtce"
    tree.write(f"{dir_path}/{file_name}", encoding="utf-8", xml_declaration=True)


def gen_xtce(args: Optional[Namespace] = None) -> None:
    """Gen_dcf main."""
    if args is None:
        args = build_parser(ArgumentParser()).parse_args()

    config = OreSatConfig(args.oresat)
    write_xtce(config, args.dir_path)
