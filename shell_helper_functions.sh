#!/bin/bash

## Helper functions for shell scripts.
__EXEC_DIR="${EXEC_DIR:-`dirname $BASH_SOURCE`}"

# All the Snakefiles are designed to run via these helper functions, and
# in fact have bootstrapping scripts on them that source this file.
export DRY_RUN=${DRY_RUN:-0}
LOCAL_CORES=${LOCAL_CORES:-4}

## Dump out the right Snakemake profile for this cluster
function gen_profile(){
    env TOOLBOX=$(find_toolbox) PATH="$(dirname "$0"):$PATH" gen_profile.py --clobber
}

function gen_local_profile(){
    gen_profile.py --template None -c "$LOCAL_CORES" --clobber
}

find_toolbox() {
    # The toolbox used by the pipeline can be set by setting TOOLBOX in the
    # environment (or environ.sh). Otherwise look for it in the program dir.
    _toolbox="$( cd $__EXEC_DIR && readlink -f ${TOOLBOX:-toolbox} )"
    echo "$_toolbox"

    if ! [ -e "$_toolbox/" ] ; then
        echo "WARNING - find_toolbox - No such directory ${_toolbox}" >&2
    fi
}

find_templates() {
    #Similarly for PanDoc templates
    _def_templates="$(readlink -f $(dirname "$BASH_SOURCE")/templates)"
    echo "${TEMPLATES:-$_def_templates}"

    if ! [ -e "${TEMPLATES:-$_def_templates}/" ] ; then
        echo "WARNING - find_templates - No such directory ${TEMPLATES:-$_def_templates}" >&2
    fi
}

# Functions to run a Snakefile
find_snakefile() {
    #Is it in the CWD (or an absolute path)?
    if [ -e "$1" ] ; then
        echo "$1"
    #Maybe it's in the folder with this script
    elif [ -e "$__EXEC_DIR/$1" ] ; then
        echo "$__EXEC_DIR/$1"
    #I give up.  Echo back the name so I get a sensible error
    else
        echo "$1"
    fi
}


### SEE doc/snakemake_be_careful.txt

snakerun_drmaa() {
    if [ "${CLUSTER_PARTITION:-}" = none ] ; then
        snakerun_single "$@"
        return
    fi

    snakefile=`find_snakefile "$1"` ; shift
    # Ensure the active VEnv gets enabled on cluster nodes:
    if [ -n "${VIRTUAL_ENV:-}" ] ; then
        export SNAKE_PRERUN="${VIRTUAL_ENV}/bin/activate"
    fi
    mkdir -p ./slurm_output

    # Save out the profile, which includes setting the right jobscript
    # TODO - maybe this should not be clobbered, to allow for manual
    # tweaking of the config?
    gen_profile || return 1

    echo
    echo "Running $snakefile in $(pwd -P) on the SLURM cluster"
    if [ -n "${EXTRA_SNAKE_FLAGS:-}" ] ; then
        echo "with extra flags: ${EXTRA_SNAKE_FLAGS}"
    fi

    [ "${VERBOSE:-0}" == 0 ] || set -x
    snakemake \
        -s "$snakefile" "$@" \
        --profile ./snakemake_profile ${EXTRA_SNAKE_FLAGS:-}
}

snakerun_single() {
    snakefile=`find_snakefile "$1"` ; shift

    gen_local_profile || return 1

    echo
    echo "Running $snakefile in $(pwd -P) in local mode"
    if [ -n "${EXTRA_SNAKE_FLAGS:-}" ] ; then
        echo "with extra flags: ${EXTRA_SNAKE_FLAGS}"
    fi

    snakemake \
        -s "$snakefile" "$@" \
        --profile ./snakemake_profile ${EXTRA_SNAKE_FLAGS:-}
}

snakerun_touch() {
    snakefile=`find_snakefile "$1"` ; shift

    echo
    echo "Running $snakefile --touch in $(pwd -P) to update file timestamps"
    snakemake -s "$snakefile" --quiet --touch "$@"
    echo "DONE"
}


if [ "$0" = "$BASH_SOURCE" ] ; then
    echo "Source this file in your BASH script to make use of the helper functions."

    echo
    echo "Here is the cluster config..."
    echo
    env TOOLBOX=$(find_toolbox) "$__EXEC_DIR"/gen_profile.py --print
fi

