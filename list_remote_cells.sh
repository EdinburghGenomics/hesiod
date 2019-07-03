#!/bin/bash
set -euo pipefail

# Basically, the job of this script is to run:
# ls -d */*/20??????_*_????????/fast?_????

# Then to digest that into a two-column TSV:
# ourname origname/library/cell

pattern='*/*/20??????_*_????????/fast?_????'

if [[ -z "$UPSTREAM" ]] ; then
    # Nothing to do
    exit 0
elif [[ "$UPSTREAM" =~ : ]] ; then
    # This works as long as there are no rogue spaces.
    ls_cmd="ssh ${UPSTREAM%%:*} cd ${UPSTREAM#*:} && ls -d $pattern"
else
    ls_cmd="cd ${UPSTREAM} && ls -d $pattern"
fi

# Chop the last dir name and condense all the results.
# Then plonk the date from the first flowcell onto the run name.
last_dir=''
last_munged=''

while read l ; do
    #echo "**$l"

    this_dir="${l%%/*}"
    if [[ "$this_dir" != "$last_dir" ]] ; then
        cell_dir="${l##*/}"
        cell_date="${cell_dir%%_*}"
        if [[ "$this_dir" =~ ^${cell_date}_ ]] ; then
            last_munged="$this_dir"
        else
            last_munged="${cell_date}_${this_dir}"
        fi
        last_dir="$this_dir"
    fi
    echo "$last_munged"$'\t'"$l"

done < <($ls_cmd | sed 's,/[^/]*$,,' | env LC_ALL=C sort -u -t/ -k1,1 -k3 )

