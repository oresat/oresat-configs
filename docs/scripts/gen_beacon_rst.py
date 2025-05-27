"""Generate beacon rst files."""

import os
import sys
from pathlib import Path

_FILE_PATH = os.path.dirname(os.path.abspath(__file__ + "/../.."))
sys.path.insert(0, _FILE_PATH)

import bitstring
import canopen

from oresat_configs import Mission, OreSatConfig

OD_DATA_TYPES = {
    canopen.objectdictionary.BOOLEAN: "bool",
    canopen.objectdictionary.INTEGER8: "int8",
    canopen.objectdictionary.INTEGER16: "int16",
    canopen.objectdictionary.INTEGER32: "int32",
    canopen.objectdictionary.INTEGER64: "int64",
    canopen.objectdictionary.UNSIGNED8: "uint8",
    canopen.objectdictionary.UNSIGNED16: "uint16",
    canopen.objectdictionary.UNSIGNED32: "uint32",
    canopen.objectdictionary.UNSIGNED64: "uint64",
    canopen.objectdictionary.REAL32: "float32",
    canopen.objectdictionary.REAL64: "float64",
    canopen.objectdictionary.VISIBLE_STRING: "str",
    canopen.objectdictionary.OCTET_STRING: "octet_str",
    canopen.objectdictionary.DOMAIN: "domain",
}
"""Nice names for CANopen data types."""


def gen_beacon_rst(config: OreSatConfig, file_path: str, url: str) -> None:
    """Genetate a rst file for a beacon definition."""

    title = "Beacon Definition"
    header_title = "AX.25 Header"
    lines = [
        f"{title}\n",
        f'{"=" * len(title)}\n',
        "\n",
        f"YAML configuration file that defines this beacon can be found at: {url}\n",
        "\n",
        f"{header_title}\n",
        f'{"-" * len(header_title)}\n',
        "\n",
    ]

    c3_od = config.od_db["c3"]
    src_callsign = c3_od["beacon"]["src_callsign"].value
    src_callsign = src_callsign + " " * (6 - len(src_callsign))
    src_ssid = c3_od["beacon"]["src_ssid"].value
    dest_callsign = c3_od["beacon"]["dest_callsign"].value
    dest_callsign = dest_callsign + " " * (6 - len(dest_callsign))
    dest_ssid = c3_od["beacon"]["dest_ssid"].value
    command = c3_od["beacon"]["command"].value
    response = c3_od["beacon"]["response"].value
    control = c3_od["beacon"]["control"].value
    pid = c3_od["beacon"]["pid"].value

    reserved_bits = 0b0110_0000
    end_of_addresses = 0b1

    dest_ssid = (dest_ssid << 1) | (int(command) << 7) | reserved_bits
    src_ssid = (src_ssid << 1) | (int(response) << 7) | reserved_bits | end_of_addresses

    header_line = (
        "+------------------+-----------------------------------+-----------+---------------------"
        "--------------+-----------+---------+-----+\n"
    )
    lines.append(header_line)
    lines.append(
        "|                  | Dest Callsign                     | Dest SSID | Src Callsign        "
        "              | Src SSID  | Control | PID |\n"
    )
    header_line = (
        "+==================+=====+=====+=====+=====+=====+=====+===========+=====+=====+=====+==="
        "==+=====+=====+===========+=========+=====+\n"
    )
    lines.append(header_line)
    header_line = header_line.replace("=", "-")
    lines.append(
        f'| Value            | "{dest_callsign[0]}" | "{dest_callsign[1]}" | "{dest_callsign[2]}" |'
        f' "{dest_callsign[3]}" | "{dest_callsign[4]}" | "{dest_callsign[5]}" | {dest_ssid:02X}    '
        f'    | "{src_callsign[0]}" | "{src_callsign[1]}" | "{src_callsign[2]}" | '
        f'"{src_callsign[3]}" | "{src_callsign[4]}" | "{src_callsign[5]}" | {src_ssid:02X}       '
        f" | {control:02X}      | {pid:02X}  |\n"
    )
    sd = (
        dest_callsign.encode()
        + dest_ssid.to_bytes(1, "little")
        + src_callsign.encode()
        + src_ssid.to_bytes(1, "little")
        + control.to_bytes(1, "little")
        + pid.to_bytes(1, "little")
    )
    lines.append(header_line)
    lines.append(
        f"| Hex              | {sd[0]:02X}  | {sd[1]:02X}  | {sd[2]:02X}  | {sd[3]:02X}  | "
        f"{sd[4]:02X}  | {sd[5]:02X}  | {sd[6]:02X}        | {sd[7]:02X}  | {sd[8]:02X}  |"
        f" {sd[9]:02X}  | {sd[10]:02X}  | {sd[11]:02X}  | {sd[12]:02X}  | {sd[13]:02X}        | "
        f"{sd[14]:02X}      | {sd[15]:02X}  |\n"
    )
    sd = (
        (bitstring.BitArray(dest_callsign.encode()) << 1).bytes
        + dest_ssid.to_bytes(1, "little")
        + (bitstring.BitArray(src_callsign.encode()) << 1).bytes
        + src_ssid.to_bytes(1, "little")
        + control.to_bytes(1, "little")
        + pid.to_bytes(1, "little")
    )
    lines.append(header_line)
    lines.append(
        f"| Hex (bitshifted) | {sd[0]:02X}  | {sd[1]:02X}  | {sd[2]:02X}  | {sd[3]:02X}  | "
        f"{sd[4]:02X}  | {sd[5]:02X}  | {sd[6]:02X}        | {sd[7]:02X}  | {sd[8]:02X}  |"
        f" {sd[9]:02X}  | {sd[10]:02X}  | {sd[11]:02X}  | {sd[12]:02X}  | {sd[13]:02X}        | "
        f"{sd[14]:02X}      | {sd[15]:02X}  |\n"
    )
    lines.append(header_line)
    lines.append(
        "| Offset           | 0   | 1   | 2   | 3   | 4   | 5   | 6         | 7   | 8   | 9   | 10"
        "  | 11  | 12  | 13        | 14      | 15  |\n"
    )
    lines.append(header_line)
    lines.append("\n")

    lines.append("Total header length: 16 octets\n")
    lines.append("\n")

    def_title = "Packet"
    lines.append(f"{def_title}\n")
    lines.append(f'{"-" * len(def_title)}\n')
    lines.append("\n")
    lines.append(".. csv-table::\n")
    lines.append(
        '   :header: "Offset", "Card", "Name", "Unit", "Data Type", "Size", "Description"\n'
    )
    lines.append("\n")
    offset = 0
    size = len(sd)
    desc = "\nax.25 packet header (see above)\n"
    desc = desc.replace("\n", "\n   ")
    lines.append(f'   "{offset}", "c3", "ax25_header", "", "octet_str", "{size}", "{desc}"\n')
    offset += size

    for obj in config.beacon_def:
        if isinstance(obj.parent, canopen.ObjectDictionary):
            index_name = obj.name
            subindex_name = ""
        else:
            index_name = obj.parent.name
            subindex_name = obj.name

        if obj.index < 0x5000:
            card = "c3"
            name = index_name
            name += "_" + subindex_name if subindex_name else ""
        else:
            card = index_name
            name = subindex_name

        if obj.data_type == canopen.objectdictionary.VISIBLE_STRING:
            size = len(obj.default)
        else:
            size = len(obj.encode_raw(obj.default))

        data_type = OD_DATA_TYPES[obj.data_type]
        desc = "\n" + obj.description + "\n"
        if obj.name in ["start_chars", "revision"]:
            desc += f": {obj.value}\n"
        if obj.name == "satellite_id":
            sat = Mission.from_id(obj.value)
            desc += f": {sat.id}\n"
        if obj.value_descriptions:
            desc += "\n\nValue Descriptions:\n"
            for value, descr in obj.value_descriptions.items():
                desc += f"\n- {value}: {descr}\n"
        if obj.bit_definitions:
            desc += "\n\nBit Definitions:\n"
            for name_, bits in obj.bit_definitions.items():
                desc += f"\n- {name_}: {bits}\n"
        desc = desc.replace("\n", "\n   ")

        lines.append(
            f'   "{offset}", "{card}", "{name}", "{obj.unit}", "{data_type}", "{size}", "{desc}"\n'
        )
        offset += size

    size = 4
    lines.append(f'   "{offset}", "c3", "crc32", "", "uint32", "{size}", "packet checksum"\n')
    offset += size

    lines.append("\n")
    lines.append(f"Total packet length: {offset} octets\n")

    dir_path = os.path.dirname(file_path)
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)

    with open(file_path, "w") as f:
        f.writelines(lines)


def gen_beacon_rst_files() -> None:
    """Generate all beacon rst files."""

    parent_dir = os.path.dirname(os.path.abspath(__file__ + "/.."))
    for mission in Mission:
        mission_name = mission.name.lower()
        url = (
            f"https://github.com/oresat/oresat-configs/blob/master/oresat_configs/{mission_name}"
            "/beacon.yaml"
        )
        file_path = f"{parent_dir}/{mission_name}/gen"
        Path(file_path).mkdir(parents=True, exist_ok=True)
        gen_beacon_rst(OreSatConfig(mission), f"{file_path}/beacon.rst", url)
