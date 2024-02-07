#!/bin/bash
set -euo pipefail

# A utility script to check the sample_names_fetch.py logic by running
# it on all the cells in an experiment
expt="$1"

export HESIOD_HOME="$(readlink -e $(dirname "$BASH_SOURCE"))"
ENVIRON_SH="${ENVIRON_SH:-$HESIOD_HOME/environ.sh}"
if [ -e "$ENVIRON_SH" ] ; then
    pushd "`dirname $ENVIRON_SH`" >/dev/null
    source "`basename $ENVIRON_SH`"
    popd >/dev/null
fi

export SAMPLE_NAMES_DIR

cells="$(cd "$PROM_RUNS"/*/"$expt" && compgen -G "*/*_*_*_*/")"

for c in $cells ; do
    c="${c%/}"
    echo "=== $c ==="

    $HESIOD_HOME/sample_names_fetch.py --debug --find --experiment "$expt" "$c" \
        || { echo "No appropriate TVS file found" ; continue ; }
    echo '---'
    $HESIOD_HOME/sample_names_fetch.py --print --experiment "$expt" "$c"
done
