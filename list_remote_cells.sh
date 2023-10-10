#!/bin/bash
set -euo pipefail

# Basically, the job of this script is to run:
# ls -d */*/20??????_*_????????/other_reports

# (It used to look for */*/20??????_*_????????/fast?_????)

# Then to digest that into a three-column TSV:
# ourname loc/origname library/cell
# The first and second columns will always correspond with a 1:1 mapping.
# The third column may provide multiple values for each name.

# Try:
# $ env UPSTREAM_LOC=prom@promethion:/data UPSTREAM_NAME=EGS1 ./list_remote_cells.sh

pattern='*/*/20??????_*_????????/other_reports'

# Prevent glob expansion in local shell
set -o noglob

if [[ -z "$UPSTREAM_LOC" ]] ; then
    # Nothing to do
    exit 0
elif [[ "$UPSTREAM_LOC" =~ : ]] ; then
    # This works as long as there are no rogue spaces. Note the fairly short
    # connection timeout - if the network is down we want to fail fast.
    ls_cmd="ssh -o ConnectTimeout=5 -T ${UPSTREAM_LOC%%:*} cd ${UPSTREAM_LOC#*:} && ls -df $pattern"
else
    ls_cmd="eval cd ${UPSTREAM_LOC} && set +o noglob && ls -df $pattern"
fi

# UPSTREAM_NAME must be set
instrument="$UPSTREAM_NAME"

# Chop the last dir name and condense all the results.
# Then plonk the date from the first flowcell onto the experiment name.
last_dir=''
last_munged=''

while read l ; do
    #echo "**$l"

    this_dir="${l%%/*}"
    cell="${l#*/}"
    if [[ "$this_dir" != "$last_dir" ]] ; then
        # Get the date from the last dir, which the machine generates.
        cell_dir="${l##*/}"
        cell_date="${cell_dir%%_*}"

        # Peel off the date and instrument from the name, if present, then
        # add them back.
        last_munged="${this_dir}"
        last_munged="${last_munged#${cell_date}_}"
        last_munged="${last_munged#${instrument}_}"
        last_munged="${cell_date}_${instrument}_${last_munged}"

        # Finally remove any spaces
        last_munged="$(tr -s ' ' '_*' <<<"$last_munged")"

        # Remember this name for all lines with this experiment name
        last_dir="$this_dir"
    fi
    echo "$last_munged"$'\t'"$UPSTREAM_LOC/$this_dir"$'\t'"$cell"

done < <($ls_cmd | sed 's,/[^/]*$,,' | env LC_ALL=C sort -u -t/ -k1,1 -k3 )

