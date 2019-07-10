#!/bin/bash
set -euo pipefail

# Basically, the job of this script is to run:
# ls -d */*/20??????_*_????????/fast?_????

# Then to digest that into a three-column TSV:
# ourname loc origname/library/cell

pattern='*/*/20??????_*_????????/fast?_????'

if [[ -z "$UPSTREAM_LOC" ]] ; then
    # Nothing to do
    exit 0
elif [[ "$UPSTREAM_LOC" =~ : ]] ; then
    # This works as long as there are no rogue spaces.
    ls_cmd="ssh ${UPSTREAM_LOC%%:*} cd ${UPSTREAM_LOC#*:} && ls -d $pattern"
    # Prevent glob expansion in local shell
    set -o noglob
else
    ls_cmd="eval cd ${UPSTREAM_LOC} && ls -d $pattern"
fi

# UPSTREAM_NAME must be set
instrument="$UPSTREAM_NAME"

# Chop the last dir name and condense all the results.
# Then plonk the date from the first flowcell onto the run name.
last_dir=''
last_munged=''

while read l ; do
    #echo "**$l"

    this_dir="${l%%/*}"
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

        # Remember this name for all lines with this run name
        last_dir="$this_dir"
    fi
    echo "$last_munged"$'\t'"$UPSTREAM_LOC"$'\t'"$l"

done < <($ls_cmd | sed 's,/[^/]*$,,' | env LC_ALL=C sort -u -t/ -k1,1 -k3 )

