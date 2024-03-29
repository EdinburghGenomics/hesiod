#!/bin/bash
set -euo pipefail
shopt -sq nullglob

#  Contents:
#    - Configuration
#    - Logging setup
#    - Python environment
#    - Action callbacks
#    - Utility functions
#    - Scanning loop

#  A driver script that is to be called directly from the CRON. Based on the similar
#  ones in Illuminatus and SMRTino.
#
#  Runs are synced from UPSTREAM_{NAME} to PROM_RUNS then, as each cell completes, the
#  files are compressed and processed into FASTQDATA, from where a report is
#  generated.
#  This script will go through all the experiments in PROM_RUNS and take action on them as
#  needed according to the state machine model. run_status.py is called to
#  determine the state. For experiments in UPSTREAM and not in PROM_RUNS an action_new
#  event is triggered.
#  As a well behaved CRON job this script should only output critical error messages
#  to STDOUT - this is controlled by the MAINLOG setting.
#  The script wants to run every 5 minutes or so, and having multiple instances
#  in flight at once is fine (and expected), though in fact there are race conditions
#  possible if two instances start at once and claim the same experiment for processing. This
#  might happen in the case of an NFS hang, but on Lustre we just assume all will be well
#  (and if not, Snakemake locking will trigger a clean failure).
#
#  Note within this script I've tried to use ( subshell blocks ) along with "set -e"
#  to emulate eval{} statements in Perl. It does work but you have to be really careful
#  on the syntax, and you have to check $? explicitly - trying to do it implicitly in
#  the manner of ( foo ) || handle_error won't do what you expect.

###--->>> CONFIGURATION <<<---###

export HESIOD_HOME="$(readlink -e $(dirname "$BASH_SOURCE"))"

# For the sake of the unit tests, we must be able to skip loading the config file,
# so allow the location to be set to, eg. /dev/null
ENVIRON_SH="${ENVIRON_SH:-$HESIOD_HOME/environ.sh}"

# This file must provide PROM_RUNS, FASTQDATA if not already set.
if [ -e "$ENVIRON_SH" ] ; then
    pushd "`dirname $ENVIRON_SH`" >/dev/null
    source "`basename $ENVIRON_SH`"
    popd >/dev/null

    # Saves having to put 'export' on every line in the config.
    export VERBOSE \
           TOOLBOX            CLUSTER_PARTITION   EXTRA_SLURM_FLAGS \
           PROM_RUNS          FASTQDATA           REPORT_DESTINATION \
           SAMPLE_NAMES_DIR \
           PROJECT_PAGE_URL   GENOLOGICSRC        REPORT_LINK \
           RSYNC_CMD          RT_SYSTEM           STALL_TIME \
           DEL_REMOTE_CELLS   PROJECT_NAME_LIST   PROM_RUNS_BATCH \
           SNAKE_THREADS      LOCAL_CORES \
           EXTRA_SNAKE_FLAGS  EXTRA_SNAKE_CONFIG  MAIN_SNAKE_TARGETS
fi

# LOG_DIR is ignored if MAINLOG is set explicitly.
LOG_DIR="${LOG_DIR:-${HOME}/hesiod/logs}"
EXP_NAME_REGEX="${EXP_NAME_REGEX:-${RUN_NAME_REGEX:-.+_.+_.+}}"

BIN_LOCATION="${BIN_LOCATION:-$HESIOD_HOME}"
#PATH="$(readlink -m $BIN_LOCATION):$PATH" # -- Needs to be done after VEnv activation
MAINLOG="${MAINLOG:-${LOG_DIR}/hesiod_driver.`date +%Y%m%d`.log}"

# 1) Sanity check these directories exist and complain to STDERR (triggering CRON
#    warning mail) if not.
for d in "${BIN_LOCATION%%:*}" "$PROM_RUNS" "$FASTQDATA" ; do
    if ! [ -d "$d" ] ; then
        echo "No such directory '$d'" >&2
        exit 1
    fi
done

###--->>> LOGGING SETUP <<<---###

# 2) Ensure that the directory is there for the main log file and set up logging
#    on file descriptor 5.
if [ "$MAINLOG" = '/dev/stdout' ] ; then
    exec 5>&1
elif [ "$MAINLOG" = '/dev/stderr' ] ; then
    exec 5>&2
else
    mkdir -p "$(dirname "$MAINLOG")" ; exec 5>>"$MAINLOG"
fi

# Main log for general messages (STDERR still goes to the CRON).
log(){ [ $# = 0 ] && cat >&5 || echo "$@" >&5 ; }

# Debug means log only if VERBOSE is set
debug(){
    if [ "${VERBOSE:-0}" != 0 ] ; then
        log "$@"
    else
        [ $# = 0 ] && cat >/dev/null || true
    fi
}

# Per-experiment log for more detailed progress messages, goes into the output
# directory. Obvously this can't be used in action_new until the directory is made.
# Main log on FD5, per-experiment log on FD6
per_expt_logname=pipeline.log
plog() {
    if [ -z "${per_expt_log:-}" ] ; then
        per_expt_log="$RUN_OUTPUT/$per_expt_logname"
        # In LOG_SPEW mode, log to the terminal too
        if [ "${LOG_SPEW:-0}" != 0 ] ; then
            exec 6> >(tee -a "$per_expt_log" >&5)
        else
            exec 6>>"$per_expt_log"
        fi
    fi
    if ! { [ $# = 0 ] && cat >&6 || echo "$@" >&6 ; } ; then
       log '!!'" Failed to write to $per_expt_log"
       log "$@"
    fi
}

plog_start() {
    # Unset $per_expt_log or else all the logs go to the first experiment seen,
    # which is horribly wrong.
    unset per_expt_log
    per_expt_logname=pipeline.log
    plog $'>>>\n>>>\n>>>'" $0 starting action_$STATUS at `date`"
}

sync_plog_start() {
    # Unset $per_expt_log or else all the logs go to the first experiment seen,
    # which is horribly wrong.
    unset per_expt_log
    per_expt_logname="sync_from_upstream.log"
    plog $'>>>\n>>>\n>>>'" $0 starting sync (status=$STATUS) at `date`"
}

# Print a message at the top of the log, and trigger one to print at the end.
intro="`date`. Running $(readlink -f "$0"); PID=$$"
log "====`tr -c '' = <<<"$intro"`==="
log "=== $intro ==="
log "====`tr -c '' = <<<"$intro"`==="
trap 'log "=== `date`. Finished run; PID=$$ ==="' EXIT

###--->>> PYTHON ENVIRONMENT <<<---###

# We always must activate a Python VEnv, unless explicitly set to 'none'
py_venv="${PY3_VENV:-default}"
if [ "${py_venv}" != none ] ; then
    if [ "${py_venv}" = default ] ; then
        log -n "Running $HESIOD_HOME/activate_venv ..."
        pushd "$HESIOD_HOME" >/dev/null
        source ./activate_venv >&5 || { log 'FAILED' ; exit 1 ; }
        popd >/dev/null
    else
        log -n "Activating Python3 VEnv from ${py_venv} ..."
        reset=`set +o | grep -w nounset` ; set +o nounset
        source "${py_venv}/bin/activate" >&5 || { log 'FAILED' ; exit 1 ; }
        $reset
    fi
    log 'VEnv ACTIVATED'
fi

# Now fix the PATH
PATH="$(readlink -m $BIN_LOCATION):$PATH"

# Tools may reliably use this to report the version of Hesiod being run right now.
# (You should look at pipeline/start_times to see which versions have touched a given experiment.)
# Note we have to do this after the VEnv activation which is after the log start so we
# can't log the version in the log header. This shouldn't matter for production as the
# full path of this script will indicate the version being run.
export HESIOD_VERSION=$(hesiod_version.py)

###--->>> ACTION CALLBACKS <<<---###

# 3) Define an action for each possible status that a promethion experiment can have:

# new)         - experiment is on upstream but not on PROM_RUNS
# sync_needed) - one or more cells to be synced (note this action is deferred)
# cell_ready)  - cell is done and we need to proces it and make an updated report

# Other states require no action, aside from maybe a log message:

# syncing)     - data is being fetched but there is nothing to process yet
# processing)  - the pipeline is working and there are no new cells to sync
# complete)    - the pipeline finished processing all known cells within experiment and made report
# aborted)     - the experiment, including any new cells added, is not to be processed further
# failed)      - the pipeline tried to process the experiment but failed somewhere
# unknown)     - anything else. ie. something is broken

# There are also some compound states

# processing_sync_needed) - treated the same as sync_needed
# processing_syncing)     - treated the same as processing

# TODO - consider if we need a separate reporting state. I guess not.

# All actions can see CELLS STATUS EXPERIMENT INSTRUMENT CELLSABORTED as reported by run_status.py,
# and RUN_OUTPUT (the input dir is simply the CWD)
# The cell_ready action can read the CELLSREADY array which is guaranteed to be non-empty

action_new(){
    # Create an input directory with a pipeline subdir and send an initial notification to RT
    # Have a 'from' file containing the upstream location
    # Also make a matching output directory and back/forth symlinks
    local cc=${#CELLS[@]}
    local exp_dir="$(dir_for_run "$EXPERIMENT")"
    local exp_dir_dir="$(dirname "$PROM_RUNS/$exp_dir")"

    local msg1 msg2

    if [ "$RUNUPSTREAM" = LOCAL ] ; then
        # The run_status.py script will report 'LOCAL' if the upstream record is missing, but we
        # then below write this value explicitly into the upstream file.
        log "\_NEW $EXPERIMENT (LOCAL) with $cc cells. Creating output directory in $FASTQDATA."
        msg1="New experiment in $PROM_RUNS with $cc cells."
    else
        log "\_NEW $EXPERIMENT with $cc cells. Creating skeleton directories in $exp_dir_dir and $FASTQDATA."
        msg1="Syncing new experiment from $RUNUPSTREAM to $exp_dir_dir with $cc cells."
    fi

    # BREAK=1 is ignored when processing new experiments from upstream, because that loop doesn't
    # check BREAK, but causes the main loop to halt when processing new local experiments found
    # by 'compgen -G'.
    # Is this ideal?
    # If something fails we should assume that something is wrong  with the FS and not try to
    # process more experiments. However, if nothing fails we can process multiple new experiments
    # in one go, be they local or remote.
    BREAK=1
    if mkdir -vp "$PROM_RUNS/$exp_dir/pipeline" |&debug ; then
        cd "$PROM_RUNS/$exp_dir"
        echo "$RUNUPSTREAM" > "pipeline/upstream"
    else
        # Don't want to get stuck in a panic loop sending multiple emails, but this is problematic
        log "FAILED $EXPERIMENT (creating $PROM_RUNS/$exp_dir/pipeline)"
        return
    fi

    # Now, this should fail if $FASTQDATA/$EXPERIMENT already exists or can't be created.
    RUN_OUTPUT="$FASTQDATA/$EXPERIMENT"
    if msg2="$(mkdir -v "$RUN_OUTPUT" 2>&1)" ; then
        debug "$msg2"
        plog_start
        log "Logging to $per_expt_log"
        plog "$msg1"
        plog "$msg2"
        chgrp -c --reference="$RUN_OUTPUT" ./pipeline |&plog
        # Links both ways, as usual
        ln -svn "$(readlink -f .)" "$RUN_OUTPUT/rundata" |&plog
        ln -svn "$(readlink -f "$RUN_OUTPUT")" "pipeline/output" |&plog
    else
        # Possibly the directory in $PROM_RUNS had been deleted and there is old data
        # in $FASTQDATA. In which case it should have been moved off the machine!
        # An error in any case, so try and fail gracefully.
        set +e
        log "$msg2"
        # Prevent writing to the pipeline log during failure handling as we don't own it!
        # But do classify the experiment so we can send the RT message to the right place.
        (  plog() { ! [ $# = 0 ] || cat >/dev/null ; }
           per_expt_log="$MAINLOG"
           classify_expt
           pipeline_fail New_Run_Setup
        )
        return
    fi

    # Now see if the experiment is internal/visitor/test
    classify_expt

    # Now detect if any cells are already complete, so we can skip the sync on the
    # next run-through. This will only be the case for local experiments - ie. those
    # copied in directly.
    check_for_ready_cells

    # Triggers a summary to be sent to RT as a comment, which should create the new RT ticket.
    # Note that there will never be a report for a brand new experiment, just a summary.
    # If this fails for some reason, press on.
    ( send_summary_to_rt comment \
                         new \
                         "$msg1"$'\n\n'"This is a new experiment - there is no report yet." \
    ) |& plog || true
    log "DONE"
}


action_cell_ready(){
    # If this is a new cell on an old experiment then maybe pipeline/type.yaml is
    # missing, so have a second chance to make it.
    if [ ! -e "pipeline/type.yaml" ] ; then
        classify_expt
    fi

    # Re-dispatch based on $EXPT_TYPE
    if [[ $(type -t action_cell_ready_"$EXPT_TYPE") == function ]] ; then
        eval action_cell_ready_"$EXPT_TYPE"
    else
        # This will also do for EXPT_TYPE=test
        action_cell_ready_unknown
    fi
}

action_cell_ready_unknown(){
    log "\_CELL_READY $EXPERIMENT. But EXPT_TYPE is $EXPT_TYPE. Taking no action."

    plog_start
    plog "Cells are ready but EXPT_TYPE is $EXPT_TYPE. Taking no further action."

    # Mark the cells complete so we don't keep trying to reprocess it
    local cell
    for cell in "${CELLSREADY[@]}" ; do
        touch_atomic "pipeline/$(cell_to_tfn "$cell").done"
    done
}

action_cell_ready_visitor(){
    log "\_CELL_READY $EXPERIMENT. Auto-delivering ${#CELLSREADY[@]} visitor cells."
    plog_start

    local cell
    for cell in "${CELLSREADY[@]}" ; do
        touch_atomic "pipeline/$(cell_to_tfn "$cell").started"
    done

    BREAK=1

    local rund="$(dirname "$PWD")"
    local based="$(basename "$PWD")"
    set +e
    for cell in "${CELLSREADY[@]}" ; do
        # I could do this in parallel but I don't think it matters
        ( set -e
          cd "$RUN_OUTPUT"
          Snakefile.checksummer --config input_dir="$rund/./$based/$cell" \
                                         output_prefix="$(basename "$cell")"
        ) |& plog
        [ $? = 0 ] || { pipeline_fail Checksumming "$cellsready_p" ; return ; }
    done
    set -e

    local run_summary
    run_summary="$(make_summary.py --expid "$EXPERIMENT" --cells "${CELLS[@]}" --fudge 2>&1 || true)"

    # Delivery logic is under qc_tools_python so we link it via a toolbox script
    local cellsready_p="$( join_cells_p "${CELLSREADY[@]}" )"
    local toolbox_path="$( cd "$HESIOD_HOME" && readlink -f "${TOOLBOX:-toolbox}" )"
    really_export EXPERIMENT
    export VISITOR_UUN="$(tyq.py '{uun}' pipeline/type.yaml)"
    env PATH="$toolbox_path:$PATH" deliver_visitor_cells "${CELLSREADY[@]}" |& plog \
        || { pipeline_fail Deliver_Visitor_Cells "$cellsready_p" ; return ; }

    # Tell RT we delivered the cells. Maybe we can close the ticket too?
    # For visitor runs, RT failure is not a critical failure.
    ( rt_runticket_manager --subject "Delivered" --reply \
        @<(echo "$(get_full_version)"
           echo
           echo "Cells were delivered to $VISITOR_UUN:"
           echo "  $cellsready_p"
           echo
           echo "----------"
           echo
           echo "$run_summary"
           echo ) ) |& plog || true

    for cell in "${CELLSREADY[@]}" ; do
        mv pipeline/$(cell_to_tfn "$cell").started pipeline/$(cell_to_tfn "$cell").done
    done
}


action_cell_ready_internal(){
    # This is the main event. Start processing and then report.
    log "\_CELL_READY $EXPERIMENT. Time to process ${#CELLSREADY[@]} cells (${#CELLSDONE[@]} already done)."
    plog_start

    local cell
    for cell in "${CELLSREADY[@]}" ; do
        touch_atomic "pipeline/$(cell_to_tfn "$cell").started"
    done

    BREAK=1

    # Printable version of CELLSREADY
    local cellsready_p="$( join_cells_p "${CELLSREADY[@]}" )"

    # This will be a no-op if the experiment isn't really complete, and will return 3
    # If contacting RT fails it will return 1, which we count as success
    local exp_complete_res
    ( notify_experiment_complete ) |&plog || exp_complete_res=$?

    # We'd like to have some project info from the LIMS (saves project_realnames.yaml)
    project_realnames

    # Do we want an RT message for every cell? Well, just a comment, and again it may fail
    ( send_summary_to_rt comment \
                         processing \
                         "Cell(s) ready: $cellsready_p. Report is at" ) |& plog || true

    # As usual, the Snakefile controls the processing
    plog "Preparing to process cell(s) $cellsready_p into $RUN_OUTPUT"
    local always_run
    set +e ; ( set -e
      log "  Starting Snakefile.main on $EXPERIMENT."

      # Log the start in a way a script can easily read back (humans can check the main log!)
      save_start_time

      # run_status.py has sanity-checked that RUN_OUTPUT is the appropriate directory,
      # and links back to ./rundata.
      # TODO - document the reason for this list of rules to always run...
      always_run=( per_cell_blob_plots  per_project_blob_tables  one_cell \
                   nanostats            convert_final_summary    sample_names )
      ( cd "$RUN_OUTPUT"

        scan_cells.py -m -r "${CELLSREADY[@]}" "${CELLSDONE[@]}" -c "${CELLS[@]}" > sc_data.yaml

        Snakefile.main ${MAIN_SNAKE_TARGETS:-copy_pod5 main} \
            -f -R "${always_run[@]}" \
            --config ${EXTRA_SNAKE_CONFIG:-}
      ) |& plog

    ) |& plog
    [ $? = 0 ] || { pipeline_fail Processing_Cells "$cellsready_p" ; return ; }

    # Check the status from earlier
    local report_status report_level
    if [ ${exp_complete_res:-0} = 3 ] ; then
        report_status="Finished cell"
        report_level=reply
    else
        report_status="Finished all cells"
        report_level=reply
    fi

    set +e ; ( set -e
      # Now we can make the report, which may be interim or final. We should only
      # ever have one of these running at a time on a given experiment.
      if ! upload_report | plog ; then
        log "Processing completed but failed to upload the report. See $per_expt_log"
        false
      fi

      # At the moment, failing notify RT after making a report is always a failure condition, even
      # if there is more data to sync/process. This should probably be addressed so we can keep
      # syncing, but it requires complex changes to the state machine.
      if ! send_summary_to_rt "$report_level" \
                              "$report_status" \
                              "Processing completed for cells $cellsready_p. Run report is at" \
                              FUDGE ;
      then
        log "Failed to send summary to RT. See $per_expt_log"
        false
      fi

      local cell
      for cell in "${CELLSREADY[@]}" ; do
          mv pipeline/$(cell_to_tfn "$cell").started pipeline/$(cell_to_tfn "$cell").done
      done

    ) |& plog ; [ $? = 0 ] || { pipeline_fail Reporting "$cellsready_p" ; return ; }

    # Attempt deletion but don't fret if it fails
    set +e ; ( set -e
        local upstream="$(cat pipeline/upstream)"
        cellsready_p="$( join_cells_p "${CELLSREADY[@]}" )"
        if [ "${DEL_REMOTE_CELLS:-no}" = yes ] ; then
            if [ ! "$upstream" = LOCAL ] && [ ! -z "$upstream" ] ; then
                log "Marking deletable cells on $upstream."
                echo "Marking cells as deletable on $upstream: $cellsready_p"
                del_remote_cells.sh "$upstream" "${CELLSREADY[@]}" || log FAILED
            fi
        fi
    ) |& plog
}


SYNC_QUEUE=()
action_sync_needed(){
    # Deferred action - add to the sync queue. No plogging just yet.
    # Note that if another experiment needs attention we may never actually get to process
    # the contents of the SYNC_QUEUE
    SYNC_QUEUE+=("$EXPERIMENT")
    log "\_SYNC_NEEDED $EXPERIMENT. Added to SYNC_QUEUE for deferred processing (${#SYNC_QUEUE[@]} items in queue)."
}

action_processing_sync_needed(){
    debug "\_PROCESSING_SYNC_NEEDED $EXPERIMENT. Calling action_sync_needed..."

    # Same as above
    action_sync_needed
}

action_incomplete(){
    debug "\_INCOMPLETE $EXPERIMENT."

    # When there are cells with no .synced flag but also no upstream to fetch from.
    # Possibly we are pushing files directly into the rundata directory?
    # No BREAK here since there is the potential for sticking in a loop. Incomplete
    # cells that will never be completed should be aborted as soon as possible.
    plog_start

    # There is one gotcha problem with this logic. If the sync fails due to upstream going
    # down then it's possible the final_summary.txt file will be there even though the
    # sync did not complete. And then, with the upstream missing, on the next run of the
    # driver we end up here. Therefore only allow the check if no upstream scanning failed.
    if [ ${#UPSTREAM_FAILS[@]} = 0 ] ; then
        check_for_ready_cells
    fi
}

action_syncing(){
    debug "\_SYNCING $EXPERIMENT."
}

action_processing_syncing(){
    debug "\_PROCESSING_SYNCING $EXPERIMENT."
}

action_processing(){
    debug "\_PROCESSING $EXPERIMENT."
}

action_failed() {
    # failed experiments need attention from an operator, so log the situatuion
    set +e
    local lastfail
    local reason=$(cat pipeline/failed 2>/dev/null)
    if [ -z "$reason" ] ; then
        # Get the last lane or sync failure message
        lastfail=$(echo pipeline/*.failed)
        reason=$(cat ${_lastfail##* } 2>/dev/null)
    fi

    log "\_FAILED $EXPERIMENT ($reason)"
}

action_aborted() {
    # aborted experiments are not our concern
    true
}

action_complete() {
    # the pipeline already fully completed for this experiment - Yay! - nothing to be done ...
    # unless another cell appears later.
    true
}

action_stripped() {
    # The data deleter is currently cleaning the experiment up. Nothing for us here.
    true
}

action_unknown() {
    # this experiment is broken somehow ... nothing to be done by the driver...
    log "\_skipping `pwd` because status is $STATUS"
}

# Not really an action but almost:
do_sync(){
    # See doc/syncing.txt
    # Called per experiment, and needs to sync all cells for which there is a remote
    # in $UPSTREAM_INFO but no {cell}.synced

    # If break was set, abort any other syncs
    if [ "$BREAK" != 0 ] ; then
        log "\_DO_SYNC $EXPERIMENT - aborting as BREAK=$BREAK"
        touch pipeline/sync.failed ; return
    fi

    log "\_DO_SYNC $EXPERIMENT"
    sync_plog_start

    # assertion - status should have been set already
    if ! [[ "$STATUS" =~ syncing ]] ; then
        log "Error - unexpected status $STATUS in do_sync"
        return
    fi

    # Work out the right SYNC_CMD. The instrument/upstream name is the second part of
    # the EXPERIMENT.
    local instrument sync_cmd
    instrument=`sed 's/[^_]\+_\([^_]\+\)_.*/\1/' <<<"$EXPERIMENT"`
    eval sync_cmd="\${SYNC_CMD_${instrument}:-}"
    sync_cmd="${sync_cmd:-$SYNC_CMD}"  # Or the default?
    sync_cmd="${sync_cmd:-false}"      # Well there should be a command :-/

    # Loop through cells
    while IFS=$'\t' read experiment upstream cell ; do

        # Note as well as $experiment we also have $run_dir set which incorporates the batch
        # directory, and $run_dir_full which is the full local path.
        # This is what should be used in the sync_cmd templates.

        plog ">>> $0 checking sync status of cell $cell at `date`"

        _cell_tfn="$(cell_to_tfn "$cell")"
        if ! [ -e "pipeline/${_cell_tfn}.synced" -o \
               -e "pipeline/${_cell_tfn}.done" ] ; then

            plog "Cell $cell needs syncing from $upstream"

            # Set upstream_host, upstream_path
            if [[ "$upstream" =~ : ]] ; then
                upstream_host="${upstream%%:*}"
            else
                upstream_host=""
            fi
            upstream_path="${upstream#*:}"

            # Run the SYNC_CMD - if the return code is 130 or 20 then abort all
            # pending ops (presume Ctrl+C was pressed) else if there is an error
            # proceed to the next experiment. Note it is essential to redirect stdin!
            # Also unset IFS to avoid re-splitting on spaces in filenames.
            IFS= eval echo "Running: $sync_cmd" | plog
            if IFS= eval $sync_cmd </dev/null |&plog ; then
                true
            elif [ $? = 130 -o $? = 20 ] ; then
                touch pipeline/sync.failed ; BREAK=1 ; return
            else
                touch pipeline/sync.failed ; return
            fi
        else
            plog "Cell $cell is already synced and/or complete"
        fi

    done < <(awk -F $'\t' -v expid="$EXPERIMENT" '$1 == expid {print}' <<<"$UPSTREAM_INFO")

    check_for_ready_cells
    mv pipeline/sync.started pipeline/sync.done
}

###--->>> UTILITY FUNCTIONS <<<---###
touch_atomic(){
    # Create a file or files but it's an error if the file already existed.
    # (Like the opposite of touch -n)
    for f in "$@" ; do
        (set -o noclobber ; >"$f")
    done
}

cell_to_tfn(){
    # Cell names are lib/cell but this can't be used as a filename
    # I think the best option is just to chop the lib/ part. Note this must
    # correspond to the logic in run_status.py which interprets the touch files.
    printf "%s" "${1##*/}"
}

really_export(){
    # Turns out that attempting to export a variable that was set with "read -a"
    # fails silently. This forces the issue. If the variable contains an array you'll
    # lose everything but the first value.
    eval local v="\$$1"

    unset "$1"
    export $1="$v"
}

qglob(){
    # Given a directory and a glob pattern, see if the pattern matches within
    # the directory.
    ( cd "$1" && compgen -G "$2" ) >/dev/null 2>&1 || return 1
}

save_start_time(){
    ( printf "%s" "$HESIOD_VERSION@" ; date +'%A, %d %b %Y %H:%M:%S' ) \
        >>pipeline/start_times
}

get_full_version(){
    # Similar to code in Illuminatus summarize_lane_contents.py
    echo "Hesiod $HESIOD_VERSION [${USER:-[unknown user]}@${HOSTNAME:-[unknown host]}:${HESIOD_HOME}]"
}

# Wrapper for ticket manager that sets the experiment and queue (note this refers
# to ~/.rt_settings not the actual queue name - set RT_SYSTEM to control which subsection
# of that file is used)
rt_runticket_manager(){
    rt_runticket_manager.py -r "$EXPERIMENT" -Q promrun_${EXPT_TYPE} -P Experiment "$@"
}

check_for_ready_cells(){
    # After a sync completes, check if any cells are now ready for processing and
    # if so write the {cell}.synced files

    # If for some reason you need to manually force all cells to be synced so the pipeline
    # will proceed:
    # $ for d in */20* ; do touch pipeline/`basename $d`.synced ; done

    # Change for MinKNOW 3.6+ the file is now named final_summary_*_*.txt but permit the
    # old name (final_summary.txt) too.
    local ready_count=0
    for cell in "${CELLSPENDING[@]}" ; do
        if qglob "$cell" "final_summary.txt" || qglob "$cell" "final_summary_*_*.txt" ; then
            ready_count=$(( $ready_count + 1 ))
            touch_atomic "pipeline/$(cell_to_tfn "$cell").synced"
            CELLSREADY+=("$cell")
        fi
    done

    if [ $ready_count -gt 0 ] ; then
        log "$ready_count cells in this experiment are now ready for processing."
    fi
}

notify_experiment_complete(){
    # Tell RT that the experiment finished. Ie. all cells seen are synced and ready to process.
    # As the number of cells in an experiment is open-ended, this may happen more than once, but
    # only once for any given total number of cells.
    local cc=${#CELLS[@]}
    local ca=${#CELLSABORTED[@]}
    local cr=${#CELLSREADY[@]}
    local cd=${#CELLSDONE[@]}
    local comment

    # Have we actually synced all the cells?
    if ! [ $(( $ca + $cr + $cd )) -eq $cc ] ; then
        # No
        return 3
    fi

    if ! [ -e pipeline/notify_${cc}_cells_complete.done ] ; then

        if [ $ca -gt 0 ] ; then
            comment=$(( $cc - $ca))" cells have run. $ca were aborted. Full report will follow soon."
        else
            comment="All $cc cells have run on the instrument. Full report will follow soon."
        fi
        rt_runticket_manager --subject processing --reply "$comment" || return $?
        touch pipeline/notify_${cc}_cells_complete.done
    fi
}

upload_report() {
    # Pushes the report to the server. On error, exits with non-zero status and guarantees
    # that pipeline/report_upload_url.txt is removed.

    # usage: upload_report

    # The SMRTino version was somewhat messier. This one tries to be sane(ish).

    # Get a handle on logging.
    plog </dev/null
    local plog_file="${per_expt_log}"

    # Push to server and capture the result (upload_report.sh runs OK and prints a URL)
    # We want stderr from upload_report.sh to go to stdout, so it gets plogged.
    # First ensure any old URL file is removed.
    rm -f pipeline/report_upload_url.txt
    log "Uploading report"
    upload_report.sh "$RUN_OUTPUT" 2>&1 >pipeline/report_upload_url.txt || \
        { log "Upload error. See $plog_file" ;
          rm -f pipeline/report_upload_url.txt ; }

    if [ ! -e pipeline/report_upload_url.txt ] ; then
        return 1
    elif ! grep -q . pipeline/report_upload_url.txt ; then
        # File exists but is empty. Shouldn't happen?!
        log "upload_report.sh exited with status 0 but did not return a URL. See $plog_file"
        rm pipeline/report_upload_url.txt
        return 1
    fi
}

join3() {
    # A general join function in Bash, with a prefix, delim and postfix
    local prefix="$1"  ; shift
    local delim="$1"   ; shift
    local postfix="$1" ; shift
    local res=""
    local i
    if [ $# -gt 0 ] ; then
        res="$1"
        shift
        for i in "$@" ; do
            res+="$delim""$i"
        done
    fi
    printf "%s%s%s" "$prefix" "$res" "$postfix"
}

join_cells_p() {
    # A specific join function for pretty-printing cells
    printf "%s" "$( join3 $'[\n\t' $',\n\t' $'\n]' "$@" )"
}

send_summary_to_rt() {
    # Sends a summary to RT. Look at pipeline/report_upload_url.txt to
    # see where the report has gone. The summary will be made by make_summary.py

    # Other than that, supply run_status and premble if you want this.
    local reply_or_comment="${1:-}"
    local run_status="${2:-}"
    local preamble="${3:-Run report is at}"
    local fudge="${4:-}"   # Set status complete after processing?

    local run_summary last_upload_report

    # We need to short-circuit this if the experiment is not an internal experiment.
    # Actually this is now done by unsetting the reporting queue in ~/.rt_settings

    # Quoting of a subject with spaces requires use of arrays but beware this:
    # https://stackoverflow.com/questions/7577052/bash-empty-array-expansion-with-set-u
    if [ -n "$run_status" ] ; then
        run_status=(--subject "$run_status")
    else
        run_status=()
    fi

    # The --fudge flag just fixes the status so the final summary doesn't show completed
    # cells as being "in_qc". Because sending the RT notification does actually complete
    # the processing.
    if [ -n "$fudge" ] ; then
        fudge=--fudge
    fi

    echo "Sending new summary of this experiment to RT."

    # This construct allows me to capture STDOUT while logging STDERR - see doc/outputter_trick.sh
    { last_upload_report="$(cat pipeline/report_upload_url.txt 2>&3)" || \
            last_upload_report="Report not yet generated."

      run_summary="$(make_summary.py --expid "$EXPERIMENT" --cells "${CELLS[@]}" $fudge 2>&3)" || \
            run_summary="Error making experiment summary."
    } 3>&1

    # Switch spaces to &nbsp; in the summary. This doesn't really fix the table but it helps a bit.
    run_summary="$(sed 's/ /\xC2\xA0/g' <<<"$run_summary")"

    # Send it all to the ticket. Log any stderr.
    ( set +u ; rt_runticket_manager "${run_status[@]}" --"${reply_or_comment}" \
        @<(echo "$(get_full_version)"
           echo
           echo "${preamble}:"
           echo "$last_upload_report"
           echo
           echo "----------"
           echo
           echo "$run_summary"
           echo ) ) 2>&1
}

dir_for_run(){
    # Decide where rundata for an experiment should live based upon PROM_RUNS_BATCH
    if [ "${PROM_RUNS_BATCH:-none}" = year ] ; then
        echo "${1:0:4}/$1"
    elif [ "${PROM_RUNS_BATCH:-none}" = month ] ; then
        echo "${1:0:4}-${1:4:2}/$1"
    else
        echo "$1"
    fi
}

pipeline_fail() {
    # Record a failure of the pipeline. The failure may be due to network outage so try
    # to report to RT but be prepared for that to fail too.

    local stage=${1:-Pipeline}
    local failure

    if [ -z "${2:-}" ] ; then
        # General failure

        # Mark the failure status
        echo "$stage on `date`" > pipeline/failed

        failure="$stage"
    else
        # Failure of a specific cell or cells
        echo "$stage on `date` for cells $2" > pipeline/failed

        failure="$stage for cells $2"
    fi

    # Send an alert to RT.
    # Note that after calling 'plog' we can query '$per_expt_log' since all shell vars are global.
    plog "Attempting to notify error to RT"
    if rt_runticket_manager --subject failed \
                            --reply "Failed at $failure."$'\n'"See log in $per_expt_log" \
                            |& plog ; then
        log "FAIL $failure on $EXPERIMENT; see $per_expt_log"
    else
        # RT failure. Complain to STDERR in the hope this will generate an alert mail via CRON
        msg="FAIL $failure on $EXPERIMENT, and also failed to report the error via RT."$'\n'"See $per_expt_log"
        echo "$msg" >&2
        log "$msg"
    fi
}

project_realnames() {
    # Save info about the projects into $RUN_OUTPUT/project_realnames.yaml
    # This is done on a best-effort basis, so if we can't contact the LIMS no file is written.
    plog "Asking RT for the real project names..."
    project_realnames.py -o "$RUN_OUTPUT/project_realnames.yaml" -t "${CELLS[@]}" |& plog || true
}

classify_expt() {
    # Decide what type of experiment this is
    # Function must be called in the run directory
    plog "Deciding if this is a visitor run or what..."
    classify_expt.py "$EXPERIMENT" > "pipeline/type.yaml"

    # Set/reset $EXPT_TYPE as a side effect
    EXPT_TYPE="$(tyq.py '{type}' pipeline/type.yaml)"
}

get_run_status() {
  # invoke run_status.py in CWD and collect some meta-information about the experiment.
  # We're passing this info to the state functions via global variables.

  # This construct allows error output to be seen in the log.
  local runstatus line v
  runstatus="$(run_status.py -I "$1" <<<"$UPSTREAM_INFO")" || \
        run_status.py -I "$1" <<<"$UPSTREAM_INFO" | log 2>&1

  # Capture the various parts into variables (see test/grs.sh)
  for v in EXPERIMENT/Experiment \
           INSTRUMENT/Instrument \
           EXPT_TYPE/Type \
           CELLS/Cells \
           CELLSPENDING/CellsPending \
           CELLSREADY/CellsReady \
           CELLSDONE/CellsDone \
           CELLSABORTED/CellsAborted \
           STATUS/PipelineStatus \
           RUNUPSTREAM/Upstream
    do
    line="$(awk -v FS=":" -v f="${v#*/}" \
                 '$1==f {gsub(/^[^:]*:[[:space:]]*/,"");print}' <<<"$runstatus")"
    IFS=$'\t' read -a "${v%/*}" <<<"$line"
  done

  # Resolve output location
  RUN_OUTPUT="$(readlink -f "$1/pipeline/output" || true)"
}

###--->>> GET INFO FROM UPSTREAM SERVER(S) <<<---###
export UPSTREAM_LOC UPSTREAM_NAME
UPSTREAM_INFO="" UPSTREAM_LOCS=() UPSTREAM_FAILS=()

for UPSTREAM_NAME in $UPSTREAM ; do
    eval UPSTREAM_LOC="\$UPSTREAM_${UPSTREAM_NAME}"
    UPSTREAM_LOCS+=("$UPSTREAM_LOC")

    # If this fails (network error or whatever) we still want to process local stuff
    log ">> Looking for ${UPSTREAM_NAME} upstream runs in $UPSTREAM_LOC"
    UPSTREAM_INFO+="$(list_remote_cells.sh 2> >(log) ; printf $)" \
        || UPSTREAM_FAILS+=("$UPSTREAM_LOC")
    # https://stackoverflow.com/questions/15184358/how-to-avoid-bash-command-substitution-to-remove-the-newline-character
    UPSTREAM_INFO=${UPSTREAM_INFO%$}
done
printf "%s" "$UPSTREAM_INFO" | debug
log "Found `printf "%s" "$UPSTREAM_INFO" | wc -l` cells in upstream runs"
unset UPSTREAM_LOC UPSTREAM_NAME

###--->>> SCANNING LOOP <<<---###

# This is more complicated than other pipelines as we have to go in stages:

# 1) Process all run directories in $PROM_RUNS
# 2) Process all new runs from $UPSTREAM_INFO
# 3) Commence all syncs (see doc/syncing.sh for why this works the way it does)

# First, account for PROM_RUNS_BATCH and see what runs are here locally.
# Remember we have nullglob set but also -u so be careful trying to access an empty list
if [ "${PROM_RUNS_BATCH:-none}" = year ] ; then
    # Look at this year plus last year. Anything older you'll have to do manually!
    this_year=$(date +%Y)
    last_year=$(date +%Y -d '1 year ago')
    prom_runs_prefix="$PROM_RUNS/($last_year|$this_year)"
    prom_runs_list=("$PROM_RUNS"/$last_year/*_*/)
    prom_runs_list+=("$PROM_RUNS"/$this_year/*_*/)
elif [ "${PROM_RUNS_BATCH:-none}" = month ] ; then
    # TODO - Should probably do the same here and look back 12 months
    prom_runs_prefix="$PROM_RUNS/\d{4}-\d{2}"
    prom_runs_list=("$PROM_RUNS"/[0-9][0-9][0-9][0-9]-[0-9][0-9]/*_*/)
else
    prom_runs_prefix="$PROM_RUNS"
    prom_runs_list=("$PROM_RUNS"/*_*/)
fi

log ">> Looking for run directories matching regex $prom_runs_prefix/$EXP_NAME_REGEX/"

# If there is nothing in "$PROM_RUNS" and nothing in "$UPSTREAM_INFO" it's an error.
# Seems best to be explicit checking this. Could be an error in the batch setting?
if [ -z "${prom_runs_list:-}" ] && [ -z "$UPSTREAM_INFO" ] ; then
    _msg="Nothing found matching $prom_runs_prefix/.*_.* or in any upstream locations (${UPSTREAM_LOCS[*]})"
    log "$_msg"
    echo "$_msg" >&2 # This will go out as a CRON error
    exit 1
fi

# For starters scan through each prom_run dir until we find something that needs dealing with.
BREAK=0
for run in "${prom_runs_list[@]}" ; do

    if ! [[ "`basename $run`" =~ ^${EXP_NAME_REGEX}$ ]] ; then
        debug "Ignoring `basename $run`"
        continue
    fi

    # TODO - consider pruning the list of runs to avoid get_run_status on every old run.

    # This sets EXPERIMENT, STATUS, etc. as a side-effect
    get_run_status "$run"

    # Taken from SMRTino - normally we don't log all the boring stuff
    if [ "$STATUS" = complete ] || \
       [ "$STATUS" = aborted  ] || \
       [ "$STATUS" = stripped ] ; then _log=debug ; else _log=log ; fi
    $_log "$EXPERIMENT with ${#CELLS[@]} cell(s) and status=$STATUS"

    # Call the appropriate function in the appropriate directory.
    pushd "$run" >/dev/null
    eval action_"$STATUS"
    # Should never actually get an error here unless the called function calls "set +e"
    [ $? = 0 ] || log "Error while trying to run action_$STATUS on $run"
    #in case this setting got clobbered...
    set -e
    popd >/dev/null

    # If the driver started some actual work it should request to break, as the CRON will start
    # a new scan at regular intervals in any case. We don't want an instance of the driver to
    # spend 2 hours processing then start working on a new run. On the other hand, we don't
    # want a problem run to gum up the pipeline if every instance of the script tries to process
    # it, quickly fails, and then exits.
    [ "$BREAK" = 0 ] || break
done

if [ "$BREAK" != 0 ] ; then
    wait ; exit
fi

# Now synthesize new run events
STATUS=new
CELLSPENDING=()
if [ -n "$UPSTREAM" ] ; then
    log ">> Handling new upstream runs matching regex $EXP_NAME_REGEX"
    [[ -n "$UPSTREAM_INFO" ]] || log "No runs seen"
    while read EXPERIMENT ; do

        # Work out where it should go based on PROM_RUNS_BATCH
        run_dir="$(dir_for_run "$EXPERIMENT")"

        if [ -e "$PROM_RUNS/$run_dir" ] ; then
            debug "Run $EXPERIMENT is not new"
            continue
        fi
        if ! [[ "$EXPERIMENT" =~ ^${EXP_NAME_REGEX}$ ]] ; then
            debug "Ignoring $EXPERIMENT due to regex"
            continue
        fi

        # Set vars to match get_run_status.
        RUNUPSTREAM=$( awk -v FS=$'\t' -v runid="$EXPERIMENT" \
                           '$1==runid {print $2}' \
                           <<<"$UPSTREAM_INFO" | head -n 1 )
        IFS=$'\t' read -a CELLS < <( awk -v FS="\t" -v ORS="\t" -v runid="$EXPERIMENT" \
                                         '$1==runid {print $3} ; END {print "\n"}' \
                                          <<<"$UPSTREAM_INFO" )

        unset per_expt_log # Should be done by plog_start in any case.
        eval action_"$STATUS"
        # Should never actually get an error here unless the called function calls "set +e"
        [ $? = 0 ] || log "Error while trying to run action_$STATUS on $EXPERIMENT"
        set -e

    done < <(printf "%s" "$UPSTREAM_INFO" | awk -F $'\t' '{print $1}' | uniq)
fi

# Now start sync events, if there are any.
BREAK=0
if [ "${#SYNC_QUEUE[@]}" != 0 ] ; then
    log ">> Processing SYNC_QUEUE"
    nn=1
    # First loop prepares to sync
    for EXPERIMENT in "${SYNC_QUEUE[@]}" ; do
        run="$EXPERIMENT"
        run_dir="$(dir_for_run "$EXPERIMENT")"
        run_dir_full="$PROM_RUNS/$run_dir"
        # Not using touch_atomic since it's possible sync.started and sync.failed are both
        # present.
        rm -f "$run_dir_full/pipeline/sync."{done,failed}
        touch "$run_dir_full/pipeline/sync.started"

        # This must be set for plog to operate
        RUN_OUTPUT="$(readlink -f "$run_dir_full/pipeline/output")"

        plog ">>> $0 preparing to sync at `date`. This run is #$nn in the queue."
        nn=$(( $nn + 1 ))
    done

    # Second loop actually syncs
    for EXPERIMENT in "${SYNC_QUEUE[@]}" ; do
        run_dir="$(dir_for_run "$EXPERIMENT")"
        run_dir_full="$PROM_RUNS/$run_dir"
        # Note this sets RUN_OUTPUT as needed for plog...
        get_run_status "$run_dir_full"

        pushd "$run_dir_full" >/dev/null
        eval do_sync
        # Should never actually get an error here unless do_sync calls "set +e"
        [ $? = 0 ] || log "Error while trying to run Rsync on $run_dir"
        set -e
        popd >/dev/null
    done
fi

wait
