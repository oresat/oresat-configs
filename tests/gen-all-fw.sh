#!/bin/bash
set -e

base=$(dirname $0)
OD=${1:-$base/od}
canopennode=${2:-$base/../CANopenNode}

# FIXME: Generate list from oresat-configs card --names once this is implemented
cards=(
    base
    c3
    battery
    adcs
    rw
    diode_test
    gps
    dxwifi
    cfc
    star_tracker
    solar
)

for name in "${cards[@]}"; do
    python -m oresat_configs fw-files $name -d $OD/$name
done

for name in "${cards[@]}"; do
    gcc -c -Wall -Wextra -Werror -I$canopennode -I$base $OD/$name/OD.c -o $OD/$name/OD.o
done
