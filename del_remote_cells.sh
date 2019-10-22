#!/bin/bash
set -euo pipefail

# This script deletes cells from the remote once they are fully processed,
# or rather it flags them for deletion by adding them to the cells_processed.txt
# file at UPSTREAM_LOC (which here is passed as an arg not an environment var).

# Deleting a cell twice (ie. duplicate lines in the file) is fine.

upstream_loc="$1" ; shift

if [ "$upstream_loc" = LOCAL ] || [ -z "$upstream_loc" ] ; then
    # Nothing to do. Really we shouldn't have been called.
    cat_cmd="true"
elif [[ "$upstream_loc" =~ : ]] ; then
    # Remote delete
    cat_cmd="ssh -T ${upstream_loc%%:*} cat >> ${upstream_loc#*:}/cells_processed.txt"
else
    # Local dir, then
    cat_cmd="eval cat >> ${upstream_loc#*:}/cells_processed.txt"
fi

( for cell in "$@" ; do echo "$cell" ; done ) | $cat_cmd
