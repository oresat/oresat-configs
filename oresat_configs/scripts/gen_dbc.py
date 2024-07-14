"""Generate a DBC file for SavvyCAN."""

from argparse import ArgumentParser, Namespace
from typing import Optional

from canopen.objectdictionary import REAL32, REAL64, UNSIGNED_TYPES, Variable

from .. import Consts, OreSatConfig, __version__

GEN_DBC = "generate dbc file for SavvyCAN"

INDENT3 = " " * 3
INDENT4 = " " * 4

VECTOR = "Vector__XXX"  # flag for default, any, all devices

CANOPEN_STATES = {
    0x00: "boot_up",
    0x04: "stopped",
    0x05: "operational",
    0x7F: "pre_operational",
}

EMCY_ERROR_CODES = {
    0x0000: "no_error",
    0x1000: "generic_error",
    0x2000: "current_error",
    0x2100: "current_device_input_error",
    0x2200: "current_inside_device_error",
    0x2300: "current_device output_error",
    0x3000: "voltage_error",
    0x3100: "mains_voltage_error",
    0x3200: "voltage_inside_device_error",
    0x3300: "output_voltage_error",
    0x4000: "temperature_error",
    0x4100: "ambient_temperature_error",
    0x4200: "device_temperature_error",
    0x5000: "device_hardware_error",
    0x6000: "device_software_error",
    0x6100: "internal_software_error",
    0x6200: "user_software_error",
    0x6300: "data_set_error",
    0x7000: "additional_modules_error",
    0x8000: "monitoring_error",
    0x8100: "communication_error",
    0x8110: "can_overrun_error",
    0x8120: "passive_mode_error",
    0x8130: "heartbeat_error",
    0x8140: "recovered_bus_error",
    0x8150: "can_id_collision_error",
    0x8200: "protocol_error",
    0x8210: "pdo_not_processed_due_to_length_error",
    0x8220: "pdo_length_exceeded_error",
    0x8230: "mpdo_not_processed_error",
    0x8240: "sync_data_length_error",
    0x8250: "rpdo_timeout_error",
    0x9000: "external_error",
    0xF000: "additional_function_error",
    0xFF00: "device_specific_error",
}

SDO_CSS = {
    0: "download_segment_request",
    1: "initiate_download_request",
    2: "initiate_upload_request",
    3: "upload_segment_request",
    4: "abort_transfer",
    5: "block_upload",
    6: "block_download",
}

SDO_SCS = {
    0: "upload_segment_response",
    1: "download_segment_respone",
    2: "initiate_upload_response",
    3: "initiate_download_response",
    4: "abort_transfer",
    5: "block_download",
    6: "block_upload",
}

SDO_ABORT_CODES = {
    0x0503_0000: "toggle_bit_not_alternated",
    0x0504_0000: "timed_out",
    0x0504_0001: "invalid_command_specifier",
    0x0504_0002: "invalid_block_size",
    0x0504_0003: "invalid_sequence_number",
    0x0504_0004: "crc_error",
    0x0504_0005: "out_of_memory",
    0x0601_0000: "unsupported_access_to_object",
    0x0601_0001: "write_only_object",
    0x0601_0002: "read_only_object",
    0x0602_0000: "object_does_not_exist",
    0x0604_0041: "object_cannot_be_mapped",
    0x0604_0042: "exceed_pdo_length",
    0x0604_0043: "general_parameter_incompatibility",
    0x0604_0047: "general_internal_incompatibility_in_device",
    0x0606_0000: "hardware_error",
    0x0607_0010: "parameter_type_does_not_match",
    0x0607_0012: "parameter_too_high",
    0x0607_0013: "parameter_too_low",
    0x0609_0011: "subindex_does_not_exist",
    0x0609_0030: "invalid_parameter_value",
    0x0609_0031: "write_value_too_high",
    0x0609_0032: "write_value_too_low",
    0x0609_0036: "maximum_less_than_minimum",
    0x060A_0023: "resource_not_available",
    0x0800_0000: "general_error",
    0x0800_0020: "data_cannot_be_transferred",
    0x0800_0021: "data_cannot_be_transferred_local_control",
    0x0800_0022: "data_cannot_be_transferred_device_state",
    0x0800_0023: "no_object_dictionary",
    0x0800_0024: "no_data_available",
}


def build_parser(parser: ArgumentParser) -> ArgumentParser:
    """Configures an ArgumentParser suitable for this script.

    The given parser may be standalone or it may be used as a subcommand in another ArgumentParser.
    """
    parser.description = GEN_DBC
    parser.add_argument(
        "--oresat",
        default=Consts.default().arg,
        choices=[m.arg for m in Consts],
        type=lambda x: x.lower().removeprefix("oresat"),
        help="Oresat Mission. (Default: %(default)s)",
    )
    parser.add_argument("-d", "--dir-path", default=".", help='directory path; default "."')
    return parser


def register_subparser(subparsers):
    """Registers an ArgumentParser as a subcommand of another parser.

    Intended to be called by __main__.py for each script. Given the output of add_subparsers(),
    (which I think is a subparser group, but is technically unspecified) this function should
    create its own ArgumentParser via add_parser(). It must also set_default() the func argument
    to designate the entry point into this script.
    See https://docs.python.org/3/library/argparse.html#sub-commands, especially the end of that
    section, for more.
    """
    parser = build_parser(subparsers.add_parser("dbc", help=GEN_DBC))
    parser.set_defaults(func=gen_dbc)


def write_dbc(config: OreSatConfig, dir_path: str = "."):
    """Write CAN message/signal definitions to a dbc file."""

    mission = config.mission.name.lower()
    file_name = mission + ".dbc"
    if dir_path:
        file_path = f"{dir_path}/{file_name}"
    else:
        file_path = file_name

    lines: list[str] = [
        f'VERSION "{__version__}"',
        "",
        "NS_ :",
        f"{INDENT4}NS_DESC_",
        f"{INDENT4}CM_",
        f"{INDENT4}BA_DEF_",
        f"{INDENT4}BA_",
        f"{INDENT4}VAL_",
        f"{INDENT4}CAT_DEF_",
        f"{INDENT4}CAT_",
        f"{INDENT4}FILTER",
        f"{INDENT4}BA_DEF_DEF_",
        f"{INDENT4}EV_DATA_",
        f"{INDENT4}ENVVAR_DATA_",
        f"{INDENT4}SGTYPE_",
        f"{INDENT4}SGTYPE_VAL_",
        f"{INDENT4}BA_DEF_SGTYPE_",
        f"{INDENT4}BA_SGTYPE_",
        f"{INDENT4}SIG_TYPE_REF_",
        f"{INDENT4}VAL_TABLE_",
        f"{INDENT4}SIG_GROUP_",
        f"{INDENT4}SIG_VALTYPE_",
        f"{INDENT4}SIGTYPE_VALTYPE_",
        f"{INDENT4}BO_TX_BU_",
        f"{INDENT4}BA_DEF_REL_",
        f"{INDENT4}BA_REL_",
        f"{INDENT4}BA_DEF_DEF_REL_",
        f"{INDENT4}BU_SG_REL_",
        f"{INDENT4}BU_EV_REL_",
        f"{INDENT4}BU_BO_REL_",
        f"{INDENT4}SG_MUL_VAL_",
        "",
        "BS_: 1000",  # bus speed in kbps
        "",
    ]

    # list of cards
    cards = config.cards
    lines.append("BU_: " + " ".join(cards) + " ")
    lines.append("")

    # general comments
    lines.append(f'CM_: "{config.mission}"')
    lines.append('CM_: "Generated by oresat-config from https://github.com/oresat/oreast-configs"')
    lines.append("")

    # SYNC
    lines.append(f"BO_ {0x80} sync: 0 c3")
    lines.append("")

    enums: list[tuple[int, str, dict[int, str]]] = []
    signal_comments: list[tuple[int, str, str]] = []
    node_comments: list[tuple[int, str]] = []
    floats: list[tuple[int, str, int]] = []
    for name, od in config.od_db.items():
        if name not in cards:
            continue

        node_comments.append((od.node_id, od.device_information.product_name))

        # EMCYs
        cob_id = 0x80 + od.node_id
        lines.append(f"BO_ {cob_id} {name}_emcy: 8 {name}")
        lines.append(f'{INDENT3}SG_ emcy_error_code : 0|16@1+ (1,0) [0|0] "" {VECTOR}')
        lines.append(f'{INDENT3}SG_ error_reg_generic : 16|1@1+ (1,0) [0|0] "" {VECTOR}')
        lines.append(f'{INDENT3}SG_ error_reg_current : 17|1@1+ (1,0) [0|0] "" {VECTOR}')
        lines.append(f'{INDENT3}SG_ error_reg_voltage : 18|1@1+ (1,0) [0|0] "" {VECTOR}')
        lines.append(f'{INDENT3}SG_ error_reg_temperature : 19|1@1+ (1,0) [0|0] "" {VECTOR}')
        lines.append(f'{INDENT3}SG_ error_reg_communication : 20|1@1+ (1,0) [0|0] "" {VECTOR}')
        signal = "error_reg_device_profile_specific"
        lines.append(f'{INDENT3}SG_ {signal} : 21|1@1+ (1,0) [0|0] "" {VECTOR}')
        signal = "error_reg_manufacturer_specific"
        lines.append(f'{INDENT3}SG_ {signal} : 23|1@1+ (1,0) [0|0] "" {VECTOR}')
        lines.append(f'{INDENT3}SG_ emcy_data : 24|40@1+ (1,0) [0|0] "" {VECTOR}')
        lines.append("")
        enums.append((cob_id, "emcy_error_code", EMCY_ERROR_CODES))

        # TPDOs
        for param_index in od:
            if param_index < 0x1800 or param_index >= 0x1A00:
                continue

            tpdo_lines = []
            mapping_index = param_index + 0x200
            tpdo = param_index - 0x1800 + 1
            cob_id = od[param_index][1].value
            sb = 0

            if name == "gps" and cob_id == 0x181:
                continue  # time sync tpdo, both c3 and gps can send this, skip for gps

            for subindex in od[mapping_index].subindices:
                if subindex == 0:
                    continue

                val = od[mapping_index][subindex].default
                mapped_index = (val >> 16) & 0xFFFF
                mapped_subindex = (val >> 8) & 0xFF
                mapped_size = val & 0xFF

                if isinstance(od[mapped_index], Variable):
                    obj = od[mapped_index]
                    signal = obj.name
                else:
                    obj = od[mapped_index][mapped_subindex]
                    signal = obj.parent.name + "_" + obj.name

                # value fields
                if not obj.bit_definitions:
                    sign = "+" if obj.data_type in UNSIGNED_TYPES else "-"
                    low = obj.min if obj.min is not None else 0
                    high = obj.max if obj.max is not None else 0
                    tpdo_lines.append(
                        f"{INDENT3}SG_ {signal} : {sb}|{mapped_size}@1{sign} ({obj.factor},0) "
                        f'[{low}|{high}] "{obj.unit}" {VECTOR}'
                    )

                    if obj.description:
                        signal_comments.append((cob_id, signal, obj.description))

                    if obj.data_type == REAL32:
                        floats.append((cob_id, signal, 1))
                    elif obj.data_type == REAL64:
                        floats.append((cob_id, signal, 2))

                # bit fields
                for n, bits in obj.bit_definitions.items():
                    n_signal = f"{signal}_{n.lower()}"
                    bits = [bits] if isinstance(bits, int) else bits
                    tpdo_lines.append(
                        f"{INDENT3}SG_ {n_signal} : {sb + max(bits)}|{len(bits)}@1+ (1,0) "
                        f'[0|0] "" {VECTOR}'
                    )

                sb += mapped_size
                if obj.value_descriptions:
                    enums.append((cob_id, signal, obj.value_descriptions))

            size = sb // 8
            lines.append(f"BO_ {cob_id} {name}_tpdo_{tpdo}: {size} {name}")
            lines += tpdo_lines
            lines.append("")

        # SDOs (useless for block SDO transfers)
        if name != "c3":
            # client / tx
            cob_id = 0x580 + od.node_id
            lines.append(f"BO_ {cob_id} {name}_sdo_tx: 8 c3")
            lines.append(f'{INDENT3}SG_ ccs M : 5|3@1+ (1,0) [0|0] "" {name}')  # multiplexor
            # ccs = 0
            lines.append(f'{INDENT3}SG_ more_segments m0 : 0|1@1+ (1,0) [0|0] "" {name}')
            lines.append(f'{INDENT3}SG_ data_padding m0 : 1|3@1+ (1,0) [0|0] "" {name}')
            lines.append(f'{INDENT3}SG_ toggle_bit m0 : 4|1@1+ (1,0) [0|0] "" {name}')
            lines.append(f'{INDENT3}SG_ segment_data m0 : 8|56@1+ (1,0) [0|0] "" {name}')
            # ccs = 1
            lines.append(f'{INDENT3}SG_ size_indicated m1 : 0|1@1+ (1,0) [0|0] "" {name}')
            lines.append(f'{INDENT3}SG_ expedited m1 : 1|1@1+ (1,0) [0|0] "" {name}')
            lines.append(f'{INDENT3}SG_ data_padding m1 : 2|2@1+ (1,0) [0|0] "" {name}')
            lines.append(f'{INDENT3}SG_ index m1 : 8|16@1+ (1,0) [0|0] "" {name}')
            lines.append(f'{INDENT3}SG_ subindex m1 : 24|8@1+ (1,0) [0|0] "" {name}')
            lines.append(f'{INDENT3}SG_ data m1 : 32|32@1+ (1,0) [0|0] "" {name}')
            # ccs = 2
            lines.append(f'{INDENT3}SG_ index m2 : 8|16@1+ (1,0) [0|0] "" {name}')
            lines.append(f'{INDENT3}SG_ subindex m2 : 24|8@1+ (1,0) [0|0] "" {name}')
            # css = 3
            lines.append(f'{INDENT3}SG_ toggle_bit m3 : 4|1@1+ (1,0) [0|0] "" {name}')
            # ccs = 4
            lines.append(f'{INDENT3}SG_ index m4 : 8|16@1+ (1,0) [0|0] "" {name}')
            lines.append(f'{INDENT3}SG_ subindex m4 : 24|8@1+ (1,0) [0|0] "" {name}')
            lines.append(f'{INDENT3}SG_ aboort_code m4 : 32|32@1+ (1,0) [0|0] "" {name}')
            # css = 5 & 6 have sub commands/multiplexor...
            lines.append("")
            enums.append((cob_id, "ccs", SDO_CSS))
            enums.append((cob_id, "aboort_code", SDO_ABORT_CODES))

            # server / rx
            cob_id = 0x600 + od.node_id
            lines.append(f"BO_ {cob_id} {name}_sdo_rx: 8 {name}")
            lines.append(f'{INDENT3}SG_ scs M : 5|3@1+ (1,0) [0|0] "" c3')  # multiplexor
            # scs = 0
            lines.append(f'{INDENT3}SG_ toggle_bit m0 : 4|1@1+ (1,0) [0|0] "" c3')
            lines.append(f'{INDENT3}SG_ data_padding m0 : 1|3@1+ (1,0) [0|0] "" c3')
            lines.append(f'{INDENT3}SG_ last_segment m0 : 0|1@1+ (1,0) [0|0] "" c3')
            lines.append(f'{INDENT3}SG_ segment_data m0 : 8|56@1+ (1,0) [0|0] "" c3')
            # scs = 1
            lines.append(f'{INDENT3}SG_ toggle_bit m1 : 4|1@1+ (1,0) [0|0] "" c3')
            # scs =2
            lines.append(f'{INDENT3}SG_ size_indicated m2 : 0|1@1+ (1,0) [0|0] "" c3')
            lines.append(f'{INDENT3}SG_ expedited m2 : 1|1@1+ (1,0) [0|0] "" c3')
            lines.append(f'{INDENT3}SG_ data_padding m2 : 2|2@1+ (1,0) [0|0] "" c3')
            lines.append(f'{INDENT3}SG_ index m2 : 8|16@1+ (1,0) [0|0] "" c3')
            lines.append(f'{INDENT3}SG_ subindex m2 : 24|8@1+ (1,0) [0|0] "" c3')
            lines.append(f'{INDENT3}SG_ data m2 : 32|32@1+ (1,0) [0|0] "" c3')
            # scs = 3
            lines.append(f'{INDENT3}SG_ index m3 : 8|16@1+ (1,0) [0|0] "" c3')
            lines.append(f'{INDENT3}SG_ subindex m3 : 24|8@1+ (1,0) [0|0] "" c3')
            # scs = 4
            lines.append(f'{INDENT3}SG_ index m4 : 8|16@1+ (1,0) [0|0] "" c3')
            lines.append(f'{INDENT3}SG_ subindex m4 : 24|8@1+ (1,0) [0|0] "" c3')
            lines.append(f'{INDENT3}SG_ aboort_code m4 : 32|32@1+ (1,0) [0|0] "" c3')
            # scs = 5 & 6 have sub commands/multiplexor...
            lines.append("")
            enums.append((cob_id, "scs", SDO_SCS))
            enums.append((cob_id, "aboort_code", SDO_ABORT_CODES))

        # heartbeats
        cob_id = 0x700 + od.node_id
        lines.append(f"BO_ {cob_id} {name}_heartbeat: 1 {name}")
        lines.append(f'{INDENT3}SG_ hearbeat : 0|8@1+ (1,0) [0|0] "" c3')
        enums.append((cob_id, "hearbeat", CANOPEN_STATES))
        lines.append("")
    lines.append("")

    # node comments
    for node_id, desc in node_comments:
        lines.append(f'CM_ BU_ {node_id} "{desc}";')
    lines.append("")

    # signal comments
    for cob_id, signal, desc in signal_comments:
        lines.append(f'CM_ SG_ {cob_id} {signal} "{desc}";')
    lines.append("")

    # signal enums
    for cob_id, signal, value_defs in enums:
        values = " ".join(f'{v} "{n}"' for v, n in value_defs.items())
        lines.append(f"VAL_ {cob_id} {signal} {values};")
    lines.append("")

    # signal floats
    for cob_id, signal, value in floats:
        lines.append(f"SIG_VALTYPE_ {cob_id} {signal} : {value};")

    with open(file_path, "w") as f:
        for line in lines:
            f.write(line + "\n")


def gen_dbc(args: Optional[Namespace] = None):
    """Gen_dbc main."""
    if args is None:
        args = build_parser(ArgumentParser()).parse_args()

    config = OreSatConfig(args.oresat)
    write_dbc(config, args.dir_path)
