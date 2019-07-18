#!/bin/bash

## Helper functions for shell scripts.
__EXEC_DIR="${EXEC_DIR:-`basename $BASH_SOURCE`}"

## boolean - are we on the new cluster or not?
function is_new_cluster(){
   [ -d /lustre/software ]
}

## Dump out the right cluster config
function cat_cluster_yml(){
    cat "`dirname $0`"/cluster.`is_new_cluster && echo slurm || echo sge`.yml
}

find_toolbox() {
    #The toolbox used by the pipeline can be set by setting TOOLBOX in the
    #environment (or environ.sh). Otherwise look for it in the program dir.
    _def_toolbox="$(readlink -f $(dirname "$BASH_SOURCE")/toolbox)"
    echo "${TOOLBOX:-$_def_toolbox}"

    if ! [ -e "${TOOLBOX:-$_def_toolbox}/" ] ; then
        echo "WARNING - find_toolbox - No such directory ${TOOLBOX:-$_def_toolbox}" >&2
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

snakerun_drmaa() {
    CLUSTER_QUEUE="${CLUSTER_QUEUE:-casava}"

    if [ "$CLUSTER_QUEUE" = none ] ; then
        snakerun_single "$@"
        return
    fi

    snakefile=`find_snakefile "$1"` ; shift
    # Ensure the active VEnv gets enabled on cluster nodes:
    if [ -n "${VIRTUAL_ENV:-}" ] ; then
        export SNAKE_PRERUN="${VIRTUAL_ENV}/bin/activate"
    fi

    # Spew out cluster.yaml
    [ -e cluster.yml ] || cat_cluster_yml > cluster.yml

    echo

    echo "Running $snakefile in `pwd -P` on the GSEG cluster"
    __SNAKE_THREADS="${SNAKE_THREADS:-100}"

    mkdir -p ./slurm_output
    set -x
    snakemake \
         -s "$snakefile" -j $__SNAKE_THREADS -p --rerun-incomplete \
         ${EXTRA_SNAKE_FLAGS:-} --keep-going --cluster-config cluster.yml \
         --jobname "{rulename}.snakejob.{jobid}.sh" \
         --drmaa " -p ${CLUSTER_QUEUE} {cluster.slurm_opts} \
                   -e slurm_output/{rule}.snakejob.%A.err \
                   -o slurm_output/{rule}.snakejob.%A.out \
                 " \
         "$@"

}

snakerun_single() {
    snakefile=`find_snakefile "$1"` ; shift

    if is_new_cluster ; then __LOCALJOBS=4 ; else __LOCALJOBS=1 ; fi

    echo
    echo "Running $snakefile in `pwd -P` in local mode"
    snakemake \
         -s "$snakefile" -j $__LOCALJOBS -p -T --rerun-incomplete \
         "$@"
}

snakerun_touch() {
    snakefile=`find_snakefile "$1"` ; shift

    echo
    echo "Running $snakefile --touch in `pwd -P` to update file timestamps"
    snakemake -s "$snakefile" --quiet --touch "$@"
    echo "DONE"
}


# All the Snakefiles have bootstrapping scripts on them, but this script
# will run snakemake directly via the shell helper functions.
export DRY_RUN=${DRY_RUN:-0}


if [ "$0" = "$BASH_SOURCE" ] ; then
    echo "Source this file in your BASH script to make use of the helper functions."

    echo
    echo "Here is the cluster config..."
    cat_cluster_yml
fi
