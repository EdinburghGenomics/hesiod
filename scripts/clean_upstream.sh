#!/bin/bash
set -euo pipefail

# This script is designed to be run on the instrument to clear out the /data
# directory.

DATADIR=/data
MODE=gui

# See if we are running in one-of the non-interactive modes
if [[ "${1:-}" == "--list" ]] ; then
    MODE=list
elif [[ "${1:-}" == "--force" ]] ; then
    MODE=force
fi

# Some global vars
alldirs=("$DATADIR"/*/)
allflags=()
for f in full partial notxt ; do
    eval "count_$f=0"
done

# A function that decides if a given dir is ready to be deleted.
function check_list(){
    _dir="$1"
    _cpt="$_dir/cells_processed.txt"
    if [[ -e "$_cpt" ]] ; then
        # Is every directory listed in cells_processed.txt?
        # I'm ignoring the case where the file is empty as this should not happen.
        for _cd in `(cd "$_dir" ; echo */*)` ; do
            if ! grep -qxF "$_cd" "$_cpt" ; then
                printf partial
                return
            fi
        done
        printf full
    else
        printf notxt
    fi
}

function mydf(){
    read _pcent _avail _target < <(df -h "$1" --output=pcent,avail,target | tail -n1)
    printf "%s" "$_target is $_pcent full with $_avail available."
}

function zeni(){
    zenity --info --text="$1" 2>/dev/null
}

function zenq(){
    zenity --question --text="$1" 2>/dev/null
}

# Let's have a look then
if [ ! -e "$alldirs" ] ; then
    echo "DATADIR $DATADIR is missing or empty"
    exit 1
fi

for (( i=0; i<${#alldirs[@]}; i++ )) ; do
    allflags[$i]=`check_list "${alldirs[$i]}"`
    eval "count_${allflags[$i]}=\$(( count_${allflags[$i]} + 1 ))"
done

if [ "$MODE" = gui ] ; then
    # Have a fake progress bar so it really looks like we're thinking about it.
    ( for (( i=0; i<${#alldirs[@]}; i++ )) ; do
        echo $(( 100 * $i / ${#alldirs[@]} ))
        sleep 0.1
      done ; echo 100
    ) | zenity --progress --text="Scanning..." --auto-close
fi

# Report to console in any case
echo "Saw ${#alldirs[@]} subdirectories in $DATADIR:"
echo "  $count_full are fully processed and ready to remove"
echo "  $count_partial are part processed"
echo "  $count_full are not processed (maybe not run dirs?)"
echo
if [[ $count_full != 0 ]] ; then
    echo "Fully processed:"
    for (( i=0; i<${#alldirs[@]}; i++ )) ; do
        if [[ ${allflags[$i]} == full ]] ; then
            echo "  `basename ${alldirs[$i]}`"
        fi
    done
    echo
fi
if [[ $count_partial != 0 ]] ; then
    echo "Part processed:"
    for (( i=0; i<${#alldirs[@]}; i++ )) ; do
        if [[ ${allflags[$i]} == partial ]] ; then
            echo "  `basename ${alldirs[$i]}`"
        fi
    done
    echo
fi
if [[ $count_notxt != 0 ]] ; then
    echo "Not processed:"
    for (( i=0; i<${#alldirs[@]}; i++ )) ; do
        if [[ ${allflags[$i]} == notxt ]] ; then
            echo "  `basename ${alldirs[$i]}`"
        fi
    done
    echo
fi

# Now see if we want to remove zem
remove=no
if [[ $MODE == gui ]] ; then
    _msg="$count_full directories in $DATADIR were fully processed by the pipeline."
    _df="`mydf "$DATADIR"`"
    _nn=$'\n\n'

    if [[ $count_full == 0 ]] ; then
        # Nowt to remove.
        zeni "${_df}${_nn}${_msg}"

    elif zenq "${_df}${_nn}${_msg}${_nn}Permanently remove them?" ; then
        remove=yes
    else
        echo "Not removing anything."
    fi
elif [[ $MODE == force ]] ; then
    remove=yes
fi

# If MODE == list then remove will never be set
if [[ $remove == yes ]] ; then
    for (( i=0; i<${#alldirs[@]}; i++ )) ; do
        if [[ ${allflags[$i]} == full ]] ; then
            echo "DUMMYRUN: rm -rf ${alldirs[$i]}"
        fi
    done

    if [[ $MODE == gui ]] ; then
        zeni "All done"
    fi
    echo "All done"
fi
