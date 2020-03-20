#!/bin/bash -l
set -euo pipefail
shopt -sq failglob
IFS=$'\t' # I'm using tab-separated lists instead of arrays

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
#  This script will go through all the runs in PROM_RUNS and take action on them as
#  needed according to the state machine model. run_status.py is called to
#  determine the state. For runs in UPSTREAM and not in PROM_RUNS an action_new
#  event is triggered.
#  As a well behaved CRON job this script should only output critical error messages
#  to STDOUT - this is controlled by the MAINLOG setting.
#  The script wants to run every 5 minutes or so, and having multiple instances
#  in flight at once is fine (and expected), though in fact there are race conditions
#  possible if two instances start at once and claim the same run for processing. This
#  might happen in the case of an NFS hang, but on Lustre we just assume all will be well!
#
#  Note within this script I've tried to use ( subshell blocks ) along with "set -e"
#  to emulate eval{} statements in Perl. It does work but you have to be really careful
#  on the syntax, and you have to check $? explicitly - trying to do it implicitly in
#  the manner of ( foo ) || handle_error won't do what you expect.
#
#  Also note the non-standard $IFS setting. If you're not sure what this does, check the
#  BASH manual.

###--->>> CONFIGURATION <<<---###

# For the sake of the unit tests, we must be able to skip loading the config file,
# so allow the location to be set to, eg. /dev/null
ENVIRON_SH="${ENVIRON_SH:-`dirname $BASH_SOURCE`/environ.sh}"

# This file must provide PROM_RUNS, FASTQDATA if not already set.
if [ -e "$ENVIRON_SH" ] ; then
    pushd "`dirname $ENVIRON_SH`" >/dev/null
    source "`basename $ENVIRON_SH`"
    popd >/dev/null

    # Saves having to put 'export' on every line in the config.
    export CLUSTER_QUEUE PROM_RUNS FASTQDATA GENOLOGICSRC \
           PROJECT_PAGE_URL REPORT_DESTINATION REPORT_LINK \
           RT_SYSTEM STALL_TIME VERBOSE TOOLBOX \
           DEL_REMOTE_CELLS PROJECT_NAME_LIST
fi

# LOG_DIR is ignored if MAINLOG is set explicitly.
LOG_DIR="${LOG_DIR:-${HOME}/hesiod/logs}"
RUN_NAME_REGEX="${RUN_NAME_REGEX:-.+_.+_.+}"

BIN_LOCATION="${BIN_LOCATION:-$(dirname "$BASH_SOURCE")}"
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
debug(){ if [ "${VERBOSE:-0}" != 0 ] ; then log "$@" ; else [ $# = 0 ] && cat >/dev/null || true ; fi ; }

# TODO - decide if PROM_RUNS needs a marker file like .smrtino uses.

# Per-run log for more detailed progress messages, goes into the output
# directory. Obvously this can't be used in action_new until the directory is made.
plog() {
    per_run_log="$RUN_OUTPUT/pipeline.log"
    if ! { [ $# = 0 ] && cat >> "$per_run_log" || echo "$@" >> "$per_run_log" ; } ; then
       log '!!'" Failed to write to $per_run_log"
       log "$@"
    fi
}

plog_start() {
    plog $'>>>\n>>>\n>>>'" $0 starting action_$STATUS at `date`"
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
        log -n "Running `dirname $BASH_SOURCE`/activate_venv ..."
        pushd "`dirname $BASH_SOURCE`" >/dev/null
        source ./activate_venv >&5 || { log 'FAILED' ; exit 1 ; }
        popd >/dev/null
    else
        log -n "Activating Python3 VEnv from ${py_venv} ..."
        reset=`set +o | grep -w nounset` ; set +o nounset
        source "${py_venv}/bin/activate" || { log 'FAILED' ; exit 1 ; }
        $reset
    fi
    log 'VEnv ACTIVATED'
fi

# Now fix the PATH
PATH="$(readlink -m $BIN_LOCATION):$PATH"

# Tools may reliably use this to report the version of Hesiod being run right now.
# (You should look at pipeline/start_times to see which versions have touched a given run.)
# Note we have to do this after the VEnv activation which is after the log start so we
# can't log the version in the log header. This shouldn't matter for production as the
# full path of this script will indicate the version being run.
export HESIOD_VERSION=$(hesiod_version.py)

###--->>> ACTION CALLBACKS <<<---###

# 3) Define an action for each possible status that a promethion run can have:

# new)         - run is on upstream but not on PROM_RUNS
# sync_needed) - one or more cells to be synced (note this action is deferred)
# cell_ready)  - cell is done and we need to proces it and make an updated report

# Other states require no action, aside from maybe a log message:

# syncing)     - data is being fetched but there is nothing to process yet
# processing)  - the pipeline is working and there are no new cells to sync
# complete)    - the pipeline has finished processing all known cells on this run and made a report
# aborted)     - the run is not to be processed further
# failed)      - the pipeline tried to process the run but failed somewhere
# unknown)     - anything else. ie. something is broken

# There are also some compound states

# processing_sync_needed) - treated the same as sync_needed
# processing_syncing)     - treated the same as processing

# TODO - consider if we need a separate reporting state. I guess not.

# All actions can see CELLS STATUS RUNID INSTRUMENT CELLSABORTED as reported by run_status.py, and
# RUN_OUTPUT (the input dir is simply the CWD)
# The cell_ready action can read the CELLSREADY array which is guaranteed to be non-empty

action_new(){
    # Create an input directory with a pipeline subdir and send an initial notification to RT
    # Have a 'from' file containing the upstream location
    # Also a matching output directory and back/forth symlinks
    _cc=`twc $CELLS`
    if [ "$RUNUPSTREAM" = LOCAL ] ; then
        # The run_status.py script will report 'LOCAL' if the upstream file is missing, but we then
        # below write this value explicitly into the upstream file.
        log "\_NEW $RUNID (LOCAL) with $_cc cells. Creating output directory in $FASTQDATA."
        _msg1="New run in $PROM_RUNS with $_cc cells."
    else
        log "\_NEW $RUNID with $_cc cells. Creating skeleton directories in $PROM_RUNS and $FASTQDATA."
        _msg1="Syncing new run from $RUNUPSTREAM to $PROM_RUNS with $_cc cells."
    fi

    # This is ignored when processing new runs from upstream, because that loop doesn't check BREAK,
    # but causes the main loop to halt when processing new local runs found by 'compgen -G'.
    # Is this ideal?
    # If something fails we should assume that something is wrong  with the FS and not try to
    # process more runs. However, if nothing fails we can process multiple new runs in one go,
    # be they local or remote.
    BREAK=1
    if mkdir -vp "$PROM_RUNS/$RUNID/pipeline" |&debug ; then
        cd "$PROM_RUNS/$RUNID"
        echo "$RUNUPSTREAM" > "pipeline/upstream"
    else
        # Don't want to get stuck in a panic loop sending multiple emails, but this is problematic
        log "FAILED $RUNID (creating $PROM_RUNS/$RUNID/pipeline)"
        return
    fi

    # Now, this should fail if $FASTQDATA/$RUNID already exists or can't be created.
    RUN_OUTPUT="$FASTQDATA/$RUNID"
    if _msg2="$(mkdir -v "$RUN_OUTPUT" 2>&1)" ; then
        debug "$_msg2"
        plog_start
        log "Logging to $per_run_log"
        plog "$_msg1"
        plog "$_msg2"
        # Links both ways, as usual
        ln -svn "$(readlink -f .)" "$RUN_OUTPUT/rundata" |&plog
        ln -svn "$(readlink -f "$RUN_OUTPUT")" "pipeline/output" |&plog
    else
        # Possibly the directory in $PROM_RUNS had been deleted and there is old data
        # in $FASTQDATA. In which case it should have been moved off the machine!
        # An error in any case. But here we do keep going.
        set +e
        log "$_msg2"
        # Prevent writing to the pipeline log during failure handling as we don't own it!
        plog() { ! [ $# = 0 ] || cat >/dev/null ; } ; per_run_log="$MAINLOG"
        pipeline_fail New_Run_Setup
        return
    fi

    # Now detect if any cells are already complete, so we can skip the sync on the
    # next run-through. This will only be the case for local runs.
    check_for_ready_cells

    # Triggers a summary to be sent to RT as a comment, which should create
    # the new RT ticket. Note that there will never be a report for a brand new run, just a summary.
    # If this fails for some reason, press on.
    ( send_summary_to_rt comment \
                         new \
                         "$_msg1"$'\n\n'"This is a new run - there is no report yet." ) |& plog || true
    log "DONE"
}

action_cell_ready(){
    # This is the main event. Start processing and then report.
    log "\_CELL_READY $RUNID. Time to process `twc $CELLSREADY` cells (`twc $CELLSDONE` already done)."
    plog_start

    for _c in $CELLSREADY ; do
        touch_atomic "pipeline/$(cell_to_tfn "$_c").started"
    done

    BREAK=1
    # Printable version of CELLSREADY
    _cellsready=$'[\n\t'"$(sed 's|\t|,\n\t|g' <<<"$CELLSREADY")"$'\n]'

    # Combined list of cells ready and done
    _cells_ready_or_done="$(tjoin $'\t' "$CELLSREADY" "$CELLSDONE")"

    # This will be a no-op if the run isn't really complete, and will return 3
    # If contacting RT fails it will return 1
    ( notify_run_complete ) |&plog || _res=$?
    if [ ${_res:-0} = 3 ] ; then
        _report_status="incomplete"
        _report_level=comment
    else
        _report_status="Finished pipeline"
        _report_level=reply
    fi

    # We'd like to have some project info from the LIMS.
    # TODO - maybe get this earlier, if we want to put the info in RT?
    project_realnames |& plog

    # Do we want an RT message for every cell? Well, just a comment, and again it may fail
    ( send_summary_to_rt comment \
                         processing \
                         "Cell(s) ready: $_cellsready. Report is at" ) |& plog || true

    # As usual, the Snakefile controls the processing
    plog "Preparing to process cell(s) $_cellsready into $RUN_OUTPUT"
    set +e ; ( set -e
      log "  Starting Snakefile.main on $RUNID."

      # Log the start in a way a script can easily read back (humans can check the main log!)
      save_start_time

      # run_status.py has sanity-checked that RUN_OUTPUT is the appropriate directory,
      # and links back to ./rundata.
      ( cd "$RUN_OUTPUT"
        Snakefile.main -f --config cellsready="$_cells_ready_or_done" cells="$CELLS" \
            -R per_cell_blob_plots per_project_blob_tables one_cell nanostats -- pack_fast5 main
      ) |& plog

    ) |& plog ; [ $? = 0 ] || { pipeline_fail Processing_Cells "$_cellsready" ; return ; }


    set +e ; ( set -e
      # Now we can make the report, which may be interim or final. We should only
      # ever have one of these running at a time.
      upload_report | plog && log DONE

      # At the moment, notifying RT after making a report is always a failure condition, even if there
      # is more data to sync/process. This should probably be addressed so we can keep syncing, but it
      # requires complex changes to the state machine.
      send_summary_to_rt "$_report_level" \
                         "$_report_status" \
                         "Processing completed for cells $_cellsready. Run report is at" \
                         FUDGE || \
      { log "Failed to send summary to RT. See $per_run_log"
        false
      }

      for _c in $CELLSREADY ; do
          mv pipeline/$(cell_to_tfn "$_c").started pipeline/$(cell_to_tfn "$_c").done
      done

    ) |& plog ; [ $? = 0 ] || { pipeline_fail Reporting "$_cellsready" ; return ; }

    # Attempt deletion but don't fret if it fails
    _upstream="`cat pipeline/upstream`"
    if [ "${DEL_REMOTE_CELLS:-no}" = yes ] ; then
        if [ ! "$_upstream" = LOCAL ] && [ ! -z "$_upstream" ] ; then
            log "Marking deletable cells on $_upstream."
            plog "Marking cells as deletable on $_upstream: $CELLSREADY"
            del_remote_cells.sh "$_upstream" $CELLSREADY |&plog || log FAILED
        fi
    fi
}


SYNC_QUEUE=""
action_sync_needed(){
    # Deferred action - add to the sync queue. No plogging just yet.
    # Note that if another run needs attention we may never actually get to process
    # the contents of the SYNC_QUEUE
    SYNC_QUEUE+="$RUNID"$'\t'
    log "\_SYNC_NEEDED $RUNID. Added to SYNC_QUEUE for deferred processing (`twc $SYNC_QUEUE` items in queue)."
}

action_processing_sync_needed(){
    debug "\_PROCESSING_SYNC_NEEDED $RUNID. Calling action_sync_needed..."

    # Same as above
    action_sync_needed
}

action_incomplete(){
    debug "\_INCOMPLETE $RUNID."

    # When there are cells with no .synced flag but also no upstream to fetch from.
    # Possibly we are writing files directly into the run dir?
    # No BREAK here since there is the potential for sticking in a loop. Incomplete
    # cells that will never be completed should be aborted as soon as possible.
    plog_start

    # There is one gotcha problem with this logic. If the sync fails due to upstream going
    # down then it's possible the final_summary.txt file will be there even though the
    # sync did not complete. And then, with the upstream missing, on the next run of the
    # driver we end up here. Therefore only allow the check if no upstream scanning failed.
    if [ -z "$UPSTREAM_FAILS" ] ; then
        check_for_ready_cells
    fi
}

action_syncing(){
    debug "\_SYNCING $RUNID."
}

action_processing_syncing(){
    debug "\_PROCESSING_SYNCING $RUNID."
}

action_processing(){
    debug "\_PROCESSING $RUNID."
}

action_failed() {
    # failed runs need attention from an operator, so log the situatuion
    set +e
    _reason=`cat pipeline/failed 2>/dev/null`
    if [ -z "$_reason" ] ; then
        # Get the last lane or sync failure message
        _lastfail=`echo pipeline/*.failed`
        _reason=`cat ${_lastfail##* } 2>/dev/null`
    fi

    log "\_FAILED $RUNID ($_reason)"
}

action_aborted() {
    # aborted runs are not our concern
    true
}

action_complete() {
    # the pipeline already fully completed for this run - Yay! - nothing to be done ...
    true
}

action_unknown() {
    # this run is broken somehow ... nothing to be done...
    log "\_skipping `pwd` because status is $STATUS"
}

# Not really an action but almost:
do_sync(){
    # See doc/syncing.txt
    # Called per run, and needs to sync all cells for which there is a remote
    # in $UPSTREAM_INFO but no {cell}.synced

    # If break was set, abort any other syncs
    if [ "$BREAK" != 0 ] ; then
        log "\_DO_SYNC $RUNID - aborting as BREAK=$BREAK"
        touch pipeline/sync.failed ; return
    fi

    log "\_DO_SYNC $RUNID"
    plog ">>> $0 starting sync (status=$STATUS) at `date`."

    # assertion - status should have been set already
    if ! [[ "$STATUS" =~ syncing ]] ; then
        log "Error - unexpected status $STATUS in do_sync"
        return
    fi

    # Work out the right SYNC_CMD. The instrument/upstream name is the second part of the RUNID.
    _instrument=`sed 's/[^_]\+_\([^_]\+\)_.*/\1/' <<<"$RUNID"`
    eval _sync_cmd="\${SYNC_CMD_${_instrument}:-}"
    _sync_cmd="${_sync_cmd:-$SYNC_CMD}"  # Or the default?
    _sync_cmd="${_sync_cmd:-false}"      # Well there should be a command :-/

    # Loop through cells
    while read run upstream cell ; do

        plog "Checking status of cell $cell"

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
            # proceed to the next run. Note it is essential to redirect stdin!
            eval echo "Running: $_sync_cmd" | plog
            if eval $_sync_cmd </dev/null |&plog ; then
                true
            elif [ $? = 130 -o $? = 20 ] ; then
                touch pipeline/sync.failed ; BREAK=1 ; return
            else
                touch pipeline/sync.failed ; return
            fi
        else
            plog "Cell $cell is already synced and/or complete"
        fi

    done < <(awk -F "$IFS" -v runid="$RUNID" '$1 == runid {print}' <<<"$UPSTREAM_INFO")

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

twc(){
    # Count the number of words in a tab-separated string. This is
    # simple when IFS=$'\t'
    printf "%s" $#
}

tjoin(){
    # Join all args with a given char. Empty arguments are excluded
    _tjoin_char="$1" ; shift
    _tjoin_res=""
    for _tjoin_arg in "$@" ; do
        _tjoin_res+="${_tjoin_char}${_tjoin_arg}"
        _tjoin_res="${_tjoin_res#${_tjoin_char}}"
        _tjoin_res="${_tjoin_res%${_tjoin_char}}"
    done
    printf "%s" "$_tjoin_res"
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

# Wrapper for ticket manager that sets the run and queue (note this refers
# to ~/.rt_settings not the actual queue name - set RT_SYSTEM to control this.)
rt_runticket_manager(){
    rt_runticket_manager.py -r "$RUNID" -Q promrun "$@"
}

check_for_ready_cells(){
    # After a sync completes, check if any cells are now ready for processing and
    # if so write the {cell}.synced files

    # If for some reason you need to manually force all cells to be synced so the pipeline
    # will proceed:
    # $ for d in */20* ; do touch pipeline/`basename $d`.synced ; done

    # Change for MinKNOW 3.6+ the file is now named final_summary_*_*.txt but permit the
    # old name (final_summary.txt) too.
    _count=0
    for cell in $CELLSPENDING ; do
        if qglob "$cell" "final_summary.txt" || qglob "$cell" "final_summary_*_*.txt" ; then
            _count=$(( $_count + 1 ))
            touch_atomic "pipeline/$(cell_to_tfn "$cell").synced"
        fi
    done

    if [ $_count -gt 0 ] ; then
        log "$_count cells on this run are now ready for processing."
    fi
}

notify_run_complete(){
    # Tell RT that the run finished. Ie. that all cells seen are synced and ready to process.
    # As the number of cells in a run is open-ended, this may happen more than once, but only
    # once for any given number of cells.

    # TODO - still needs to trigger from cell_ready and be tested
    _cc=`twc $CELLS`
    _ca=`twc $CELLSABORTED`
    _cr=`twc $CELLSREADY`
    _cd=`twc $CELLSDONE`

    # Have we actually synced all the cells?
    if ! [ $(( $_ca + $_cr + $_cd )) -eq $_cc ] ; then
        # No
        return 3
    fi

    if ! [ -e pipeline/notify_${_cc}_cells_complete.done ] ; then

        if [ $_ca -gt 0 ] ; then
            _comment=$(( $_cc - $_ca))" cells have run. $_ca were aborted. Full report will follow soon."
        else
            _comment="All $_cc cells have run on the instrument. Full report will follow soon."
        fi
        rt_runticket_manager --subject processing --reply "$_comment" || return $?
        touch pipeline/notify_${_cc}_cells_complete.done
    fi
}

upload_report() {
    # Pushes the report. Will not exit on error but the report_upload_url.txt will indicate
    # if this worked.
    # status to the caller. I'm assuming all substantial processing will have been done already
    # so this should be quick.

    # usage: upload_report

    # The SMRTino version was somewhat messier. This may get messier too.

    set +o | grep '+o errexit' && _ereset='set +e' || _ereset='set -e'
    set +e

    # Get a handle on logging.
    plog </dev/null
    _plog="${per_run_log}"

    # Push to server and capture the result (if upload_report.sh does not error it must print a URL)
    # We want stderr from upload_report.sh to go to stdout, so it gets plogged.
    # Note that the code relies on checking the existence of this file to see if the upload worked,
    # so if the upload fails it needs to be removed.
    rm -f pipeline/report_upload_url.txt
    log "Uploading report"
    upload_report.sh "$RUN_OUTPUT" 2>&1 >pipeline/report_upload_url.txt || \
        { log "Upload error. See $_plog" ;
          rm -f pipeline/report_upload_url.txt ; }

    eval "$_ereset"
}

send_summary_to_rt() {
    # Sends a summary to RT. Look at pipeline/report_upload_url.txt to
    # see where the report has gone. The summary will be made by make_summary.py

    # Other than that, supply run_status and premble if you want this.
    _reply_or_comment="${1:-}"
    _run_status="${2:-}"
    _preamble="${3:-Run report is at}"
    _fudge="${4:-}"

    # Quoting of a subject with spaces requires use of arrays but beware this:
    # https://stackoverflow.com/questions/7577052/bash-empty-array-expansion-with-set-u
    if [ -n "$_run_status" ] ; then
        _run_status=(--subject "$_run_status")
    else
        _run_status=()
    fi

    # The --fudge flag just fixes the status so the final summary doesn't show completed
    # cells as being "in_qc". Because sending the RT notification does actually complete
    # the processing.
    if [ -n "$_fudge" ] ; then
        _fudge=--fudge
    fi

    echo "Sending new summary of this run to RT."

    # This construct allows me to capture STDOUT while logging STDERR - see doc/outputter_trick.sh
    { _last_upload_report="$(cat pipeline/report_upload_url.txt 2>&3)" || \
            _last_upload_report="Report not yet generated or upload failed."

      _run_summary="$(make_summary.py --runid "$RUNID" --cells "$CELLS" $_fudge 2>&3)" || \
            _run_summary="Error making run summary."
    } 3>&1

    # Switch spaces to &nbsp; in the summary. This doesn't really fix the table but it does help.
    _run_summary="$(sed 's/ /\xC2\xA0/g' <<<"$_run_summary")"

    # Send it all to the ticket. Log any stderr.
    ( set +u ; rt_runticket_manager "${_run_status[@]}" --"${_reply_or_comment}" \
        @<(echo "${_preamble}:"
           echo "$_last_upload_report"
           echo
           echo "----------"
           echo
           echo "$_run_summary"
           echo ) ) 2>&1
}

pipeline_fail() {
    # Record a failure of the pipeline. The failure may be due to network outage so try
    # to report to RT but be prepared for that to fail too.

    stage=${1:-Pipeline}

    if [ -z "${2:-}" ] ; then
        # General failure

        # Mark the failure status
        echo "$stage on `date`" > pipeline/failed

        _failure="$stage"
    else
        # Failure of a specific cell or cells
        echo "$stage on `date` for cells $2" > pipeline/failed

        _failure="$stage for cells $2"
    fi

    # Send an alert to RT.
    # Note that after calling 'plog' we can query '$per_run_log' since all shell vars are global.
    plog "Attempting to notify error to RT"
    if rt_runticket_manager --subject failed --reply "Failed at $_failure."$'\n'"See log in $per_run_log" |& plog ; then
        log "FAIL $_failure on $RUNID; see $per_run_log"
    else
        # RT failure. Complain to STDERR in the hope this will generate an alert mail via CRON
        msg="FAIL $_failure on $RUNID, and also failed to report the error via RT."$'\n'"See $per_run_log"
        echo "$msg" >&2
        log "$msg"
    fi
}

project_realnames() {
    # Save info about the projects into $RUN_OUTPUT/project_realnames.yaml
    # This is done on a best-effort basis, so if we can't contact the LIMS no file is written.
    plog "Asking LIMS for the real project names..."
    project_realnames.py -o "$RUN_OUTPUT/project_realnames.yaml" -t $CELLS || true
}

get_run_status() { # run_dir
  # invoke run_status.py in CWD and collect some meta-information about the run.
  # We're passing this info to the state functions via global variables.

  # This construct allows error output to be seen in the log.
  _runstatus="$(run_status.py -I "$1" <<<"$UPSTREAM_INFO")" || \
        run_status.py -I "$1" <<<"$UPSTREAM_INFO" | log 2>&1

  # Capture the various parts into variables (see test/grs.sh)
  for _v in RUNID/RunID INSTRUMENT/Instrument \
            CELLS/Cells CELLSPENDING/CellsPending CELLSREADY/CellsReady CELLSDONE/CellsDone CELLSABORTED/CellsAborted \
            STATUS/PipelineStatus RUNUPSTREAM/Upstream ; do
    _line="$(awk -v FS=":" -v f="${_v#*/}" '$1==f {gsub(/^[^:]*:[[:space:]]*/,"");print}' <<<"$_runstatus")"
    eval "${_v%/*}"='"$_line"'
  done

  # Resolve output location
  RUN_OUTPUT="$(readlink -f "$1/pipeline/output" || true)"
}

###--->>> GET INFO FROM UPSTREAM SERVER(S) <<<---###
export UPSTREAM_LOC UPSTREAM_NAME
UPSTREAM_INFO="" UPSTREAM_LOCS="" UPSTREAM_FAILS=""

# Note because of the IFS setting we need to munge $UPSTREAM
for UPSTREAM_NAME in `tr ' ' '\t' <<<$UPSTREAM` ; do
    eval UPSTREAM_LOC="\$UPSTREAM_${UPSTREAM_NAME}"
    UPSTREAM_LOCS+="$UPSTREAM_LOC"$'\t'

    # If this fails (network error or whatever) we still want to process local stuff
    log ">> Looking for ${UPSTREAM_NAME} upstream runs in $UPSTREAM_LOC"
    UPSTREAM_INFO+="$(list_remote_cells.sh 2> >(log) ; printf $)" || UPSTREAM_FAILS+="$UPSTREAM_LOC"$'\t'
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

log ">> Looking for run directories matching regex $PROM_RUNS/$RUN_NAME_REGEX/"

# If there is nothing in "$PROM_RUNS" and nothing in "$UPSTREAM_INFO" it's an error.
# Seems best to be explicit checking this.
if ! compgen -G "$PROM_RUNS/*/" >/dev/null && [ -z "$UPSTREAM_INFO" ] ; then
    _msg="Nothing found in $PROM_RUNS or any upstream locations (${UPSTREAM_LOCS% })"
    log "$_msg"
    echo "$_msg" >&2 # This will go out as a CRON error
    exit 1
fi

# Now scan through each prom_run dir until we find something that needs dealing with.
BREAK=0
if compgen -G "$PROM_RUNS/*/" >/dev/null ; then for run in "$PROM_RUNS"/*/ ; do

    if ! [[ "`basename $run`" =~ ^${RUN_NAME_REGEX}$ ]] ; then
        debug "Ignoring `basename $run`"
        continue
    fi

    # This sets RUNID, STATUS, etc.
    get_run_status "$run"

    # Taken from SMRTino - normally we don't log all the boring stuff
    if [ "$STATUS" = complete ] || [ "$STATUS" = aborted ] ; then _log=debug ; else _log=log ; fi
    $_log "$RUNID with `twc $CELLS` cell(s) and status=$STATUS"

    #Call the appropriate function in the appropriate directory.
    { pushd "$run" >/dev/null && eval action_"$STATUS"
    } || log "Error while trying to run action_$STATUS on $run"
    popd >/dev/null
    #in case this setting got clobbered...
    set -e

    # If the driver started some actual work it should request to break, as the CRON will start
    # a new scan at regular intervals in any case. We don't want an instance of the driver to
    # spend 2 hours processing then start working on a new run. On the other hand, we don't
    # want a problem run to gum up the pipeline if every instance of the script tries to process
    # it, fails, and then exits.
    [ "$BREAK" = 0 ] || break
done ; fi

if [ "$BREAK" != 0 ] ; then
    wait ; exit
fi

# Now synthesize new run events
STATUS=new
if [ -n "$UPSTREAM" ] ; then
    log ">> Handling new upstream runs matching regex $RUN_NAME_REGEX"
    [[ -n "$UPSTREAM_INFO" ]] || log "No runs seen"
    while read RUNID ; do
        if [ -e "$PROM_RUNS/$RUNID" ] ; then
            debug "Run $RUNID is not new"
            continue
        fi
        if ! [[ "$RUNID" =~ ^${RUN_NAME_REGEX}$ ]] ; then
            debug "Ignoring $RUNID due to regex"
            continue
        fi

        # Set vars to match get_run_status. Remember we have IFS set globally to "\t" in this script.
        RUNUPSTREAM=$(awk -v FS="$IFS" -v runid="$RUNID" '$1==runid {print $2}' <<<"$UPSTREAM_INFO" | head -n 1)
        CELLS=$(awk -v FS="$IFS" -v ORS="$IFS" -v runid="$RUNID" '$1==runid {print $3}' <<<"$UPSTREAM_INFO")
        CELLS="${CELLS%$IFS}" # chop trailing tab
        CELLSPENDING=""

        { eval action_"$STATUS"
        } || log "Error while trying to run action_$STATUS on $RUNID"

    done < <(printf "%s" "$UPSTREAM_INFO" | awk -F "$IFS" '{print $1}' | uniq)
fi

# Now start sync events. Note that due to set -eu I need to check explicitly for the empty list.
BREAK=0
if [ -n "${SYNC_QUEUE:-}" ] ; then
    log ">> Processing SYNC_QUEUE"
    _nn=1
    for RUNID in $SYNC_QUEUE ; do
        # Not using touch_atomic since it's possible sync.started and sync.failed are both
        # present.
        rm -f "$PROM_RUNS/$RUNID/pipeline/sync."{done,failed}
        touch "$PROM_RUNS/$RUNID/pipeline/sync.started"

        # This must be set for plog to operate
        RUN_OUTPUT="$(readlink -f "$PROM_RUNS/$RUNID/pipeline/output")"

        plog ">>> $0 preparing to sync at `date`. This run is #$_nn in the queue."
        _nn=$(( $_nn + 1 ))
    done

    for RUNID in $SYNC_QUEUE ; do
        # Note this sets RUN_OUTPUT as needed for plog...
        get_run_status "$PROM_RUNS/$RUNID"

        { pushd "$PROM_RUNS/$RUNID" >/dev/null && eval do_sync
        } || log "Error while trying to run Rsync on $PROM_RUNS/$RUNID"
        popd >/dev/null
    done
fi

wait
