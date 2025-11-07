# OreSat Configs

Firmware/software configurations for OreSat missions.

Includes:

- A centralize "database" for all OreSat card object dictionaries (OD)
- Beacon definition for each OreSat mission
- The C3 F-RAM data definition (object values to be saved to the F-RAM chip)

Having all the OD defined in one place makes it much easier to update
OD definitions without having to go to each repo to update each cards OD.
Also, the C3 can easily import all the OD definitions to be used for SDO
transfers.

## How This Works

- All object dictionaries for a specific OreSat mission are defined by [YAML]
  files.
  - All the OD configs are in `oresat_configs/base/`
  - All the beacon configs (`beacon.yaml`)are in their mission directories: 
    `oresat_configs/oresat<mission_num>/`
- All card specific configs are are named `<card_name>.yaml` format.
  They contain all card specific objects and PDOs.
  - **NOTE:** The cards YAML are similar to CANopen's `.eds` files; they are
    for a device type, not a unique device on a CAN network (if you add an
    object to `solar.yaml`, all solar cards will have that object).
- The `sw_common.yaml` defines all CANopen standard objects, common objects,
  and common PDOs for all Octavo A8-based cards.
- The `fw_common.yaml` defines all CANopen standard objects, common objects,
  and common PDOs for all STM32-based cards.
- A `standard_object.yaml` contains some CANopen standard objects that any
  `<card_name>.yaml` or `*_common.yaml` can flag to include.
- The `beacon.yaml` file defines the beacon definition as all the data is
  pulled strait out the C3's OD, which is mostly build from all other ODs.
- The `c3.yaml` file also defines what objects have their values periodically
  saved to the C3's F-RAM chip.

## Setup

For regular users: `libyaml` should be installed by default on
reasonable systems, but it never hurts to make sure.

```bash
$ sudo apt install libyaml-0-2
$ pip install oresat-configs
```
For developers:
```bash
$ sudo apt install libyaml-0-2
$ pip install -e .[dev]
```


If installing on ARM (e.g. Octavo cards like the C3) special work is needed to
ensure that `pyyaml` uses the `libyaml` C bindings. The binary wheels from PyPI
aren't built with them so we need to install from the source package:

Installing the first time:
```bash
$ sudo apt install libyaml-dev
$ pip install --no-binary pyyaml oresat-configs
```

Fixing an already installed pyyaml: (see here if you get "ImportError: pyyaml
missing/installed without libyaml bindings.")
```bash
$ sudo apt install libyaml-dev
$ pip install --force-reinstall --no-cache-dir --no-binary pyyaml pyyaml
```

## Updating a Config

After updating configs for card(s), run the unit tests to validate all the
configs.

```bash
$ python3 -m unittest
```

If there are no errors, the configs are valid.

Build and install the new version of oresat-configs to build, test, and/or
import with.

Once the change have been tested with firmware/software, open a Pull
Request to this repo to get all changes into the next release.

## Building a distributable package

```bash
$ python -m build
```
The artifact will be in dist/oresat_configs-*.whl


[YAML]: https://en.wikipedia.org/wiki/YAML
