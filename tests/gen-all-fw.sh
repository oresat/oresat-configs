#!/bin/bash
set -e

base=$(dirname $0)
OD=${1:-$base/od}
canopennode=${2:-$base/../CANopenNode}

cards=($(python -m oresat_configs cards --names))

for name in "${cards[@]}"; do
    python -m oresat_configs fw-files $name -d $OD/$name
done

for name in "${cards[@]}"; do
    gcc -c -Wall -Wextra -Werror -I$canopennode -I$base $OD/$name/OD.c -o $OD/$name/OD.o
done
