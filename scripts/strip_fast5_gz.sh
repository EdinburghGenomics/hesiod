#!/bin/bash

# Around March 2022 I updated Hesiod so that the fast5 files were no longer gzip compressed.
# The new files do not benefit from compression, so it's much simpler just to hard link them.
# The thing is that when I re-ran the pipeline over multiple runs I now have redundant files.

# PLN is:

# for each run, look for .fast5.gz files. If there is a corresponding .fast5 then check the
# md5sum. If that matches we can remove the .fast5.gz.

# OK

set -euo pipefail

TOP_LEVEL_DIR=/lustre-gseg/promethion/prom_fastqdata
TRASH="$TOP_LEVEL_DIR/trash"

runs=("$TOP_LEVEL_DIR"/2022032*)

for arun in "${runs[@]}" ; do

    [ -e "$arun" ] || { echo "No such dir $arun" ; break ; }

    echo "Processing $arun"

    nn=0
    while read -d $'\0' f5gz ; do
        nn=$(( $nn + 1 ))
        printf "%s %s\n" $nn "$(basename "$f5gz")"

        f5="${f5gz%%.gz}"
        if [ -e "$f5" ] ; then
            # $f5gz is a candidate for removal. But we're going to md5sum check to be sure

            # We need the path to "$f5" relative to "$arun"
            f5_rel="./${f5:${#arun}}"

            f5md5sum="$arun/md5sums/$f5_rel.md5"

            if [ ! -e "$f5md5sum" ] ; then
                echo "Error - missing $f5md5sum"
                exit 1
            fi

            sum1=$(awk '{print $1}' "$f5md5sum")
            sum2=$(zcat "$f5gz" | md5sum - | awk '{print $1}')
            if [ "$sum1" != "$sum2" ] ; then
                echo "md5sum mismatch in $f5gz"
                exit 1
            fi

            # Now we can trash!
            f5_reldir="./${f5:${#TOP_LEVEL_DIR}}"
            f5_reldir="$(dirname "$f5_reldir")"
            mkdir -vp "$TRASH/$f5_reldir"
            mv -vt "$TRASH/$f5_reldir" "$f5gz" "$arun/md5sums/$f5_rel.gz.md5"


        fi

    done < <(find "$arun"/*/*/fast5_* -name '*.fast5.gz' -print0)

    echo "Found $nn fast5.gz files in $arun"
    sleep 5

done


