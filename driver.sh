#!/bin/bash -l
set -euo pipefail
shopt -sq failglob

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
#  needed according to the state machine model. prom_run_status.py is called to
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

###--->>> CONFIGURATION <<<---###

# For the sake of the unit tests, we must be able to skip loading the config file,
# so allow the location to be set to, eg. /dev/null
ENVIRON_SH="${ENVIRON_SH:-`dirname $BASH_SOURCE`/environ.sh}"

# This file must provide FROM_LOCATION, TO_LOCATION if not already set.
if [ -e "$ENVIRON_SH" ] ; then
    pushd "`dirname $ENVIRON_SH`" >/dev/null
    source "`basename $ENVIRON_SH`"
    popd >/dev/null

    # Saves having to put 'export' on every line in the config.
    export CLUSTER_QUEUE PROM_RUNS FASTQDATA GENOLOGICSRC \
           PROJECT_PAGE_URL REPORT_DESTINATION REPORT_LINK \
           RT_SYSTEM STALL_TIME VERBOSE
fi

# Tools may reliably use this to report the version of Hesiod being run right now.
# They should look at pipeline/start_times to see which versions have touched a given run.
export HESIOD_VERSION=$(cat "$(dirname $BASH_SOURCE)"/version.txt || echo unknown)

# LOG_DIR is ignored if MAINLOG is set explicitly.
LOG_DIR="${LOG_DIR:-${HOME}/hesiod/logs}"
RUN_NAME_REGEX="${RUN_NAME_REGEX:-.+_.+_.+}"

BIN_LOCATION="${BIN_LOCATION:-$(dirname $0)}"
PATH="$(readlink -m $BIN_LOCATION):$PATH"
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
# directory. Obvously this can't be used in action_new.
plog() {
    per_run_log="$RUN_OUTPUT/pipeline.log"
    if ! { [ $# = 0 ] && cat >> "$per_run_log" || echo "$*" >> "$per_run_log" ; } ; then
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

# All actions can see CELLS STATUS RUNID INSTRUMENT CELLSABORTED as reported by prom_run_status.py, and
# RUN_OUTPUT (the input dir is simply the CWD)
# The cell_ready action can read the CELLSREADY array which is guaranteed to be non-empty

action_new(){
    # Create an input directory with a pipeline subdir and send an initial notification to RT
    # Have a 'from' file containing the upstream location
    # Also a matching output directory and back/forth symlinks
    # If something fails we should assume that something is wrong  with the FS and not try to
    # process more runs. However, if nothing fails we can process multiple new runs in one go.

    log "\_NEW $RUNID. Creating skeleton directories in $PROM_RUNS and $FASTQDATA."

    if mkdir -vp "$PROM_RUNS/$RUNID/pipeline" |&debug ; then
        cd "$PROM_RUNS/$RUNID"
        echo "$UPSTREAM_LOC" > "pipeline/upstream"
    else
        # Don't want to get stuck in a panic loop sending multiple emails, but this is problematic
        log "FAILED $RUNID (creating $PROM_RUNS/$RUNID/pipeline)"
        BREAK=1
        return
    fi

    # Now, this should fail if $FASTQDATA/$RUNID already exists or can't be created.
    RUN_OUTPUT="$FASTQDATA/$RUNID"
    if _msg="$(mkdir -v "$RUN_OUTPUT")" ; then
        plog_start
        plog "$_msg"
        # Links both ways, as usual
        ln -svn "$(readlink -f .)" "$RUN_OUTPUT/rundata" |&plog
        ln -svn "$(readlink -f "$RUN_OUTPUT")" "pipeline/output" |&plog
    else
        # Possibly the directory in $PROM_RUNS had been deleted and there is old data
        # in $FASTQDATA. In which case it should have been moved off the machine!
        # An error in any case. But here we do keep going.
        msg="Either $FASTQDATA/$RUNID already existed or could not be created."
        set +e
        log "$msg" ; plog "$msg"
        pipeline_fail New_Run_Setup
    fi

    # Triggers a summary to be sent to RT as a comment, which should create
    # the new RT ticket.
    # FIXME - add more actual content like the other pipelines
    rt_runticket_manager --comment @<(echo "Syncing new run from $UPSTREAM_LOC with ${#UPSTREAM_CELLS[@]} cells.") |& \
        plog && log "DONE"
}

SYNC_QUEUE=()

action_sync_needed(){
    # Deferred action - add to the sync queue
    debug "\_SYNC_NEEDED $RUNID. Adding to SYNC_QUEUE for deferred processing (${#SYNC_QUEUE[@]} items in queue)."

    SYNC_QUEUE+=($RUNID)
}

action_processing_sync_needed(){
    # Same as above
    action_sync_needed
}

###--->>> UTILITY FUNCTIONS <<<---###
touch_atomic(){
    # Create a file or files but it's an error if the file already existed.
    # (Like the opposite of touch -n)
    for f in "$@" ; do
        (set -o noclobber ; >"$f")
    done
}

save_start_time(){
    ( echo -n "$HESIOD_VERSION@" ; date +'%a %b %_d %H:%M:%S %Y' ) \
        >>"$RUN_OUTPUT"/pipeline/start_times
}

# Wrapper for ticket manager that sets the run and queue
rt_runticket_manager(){
    rt_runticket_manager.py -r "$RUNID" -Q promrun "$@"
}

notify_run_complete(){
    # Tell RT that the run finished. Ie. that all cells seen are synced and ready to process.
    # As the number of cells in a run is open-ended, this may happen more than once, but only
    # once for any given number of cells.
    if ! [ -e "$RUN_OUTPUT"/pipeline/notify_${n}_cells_complete.done ] ; then

        # FIXME - this is still code from SMRTino
        _cc=`wc -w <<<"$CELLS"`
        _ca=`wc -w <<<"$CELLSABORTED"`
        if [ $_ca -gt 0 ] ; then
            _comment=$(( $_cc - $_ca))" SMRT cells have run. $_ca were aborted. Final report will follow soon."
        else
            _comment="All $_cc SMRT cells have run on the instrument. Final report will follow soon."
        fi
        if rt_runticket_manager --subject processing --reply "$_comment" ; then
            touch "$RUN_OUTPUT"/pbpipeline/notify_run_complete.done
        fi
    fi
}

run_report() {
    # Makes a report. Will not exit on error. I'm assuming all substantial processing
    # will have been done by Snakefile.process_cells so this should be quick.

    # usage: run_report [rt_prefix] [report_fudge_status] [rt_set_status]

    # rt_prefix is mandatory and should be descriptive
    # A blank report_fudge_status will cause the status to be determined from the
    # state machine, but sometimes we want to override this.
    # A blank rt_set_status will leave the status unchanged. A value of "NONE" will
    # suppress reporting to RT entirely.
    # Caller is responsible for log redirection to plog, but in some cases we want to
    # make a regular log message referencing the plog destination, so this is a bit messy.
    set +o | grep '+o errexit' && _ereset='set +e' || _ereset='set -e'
    set +e

    # All of these must be supplied.
    _rprefix="$1"
    _rep_status="$2"
    _rt_run_status="$3"

    # Get a handle on logging.
    plog </dev/null
    _plog="${per_run_log}"

    ( cd "$RUN_OUTPUT" ; Snakefile.report -F --config rep_status="$_rep_status" -- report_main ) 2>&1

    # Snag that return value
    _retval=$(( $? + ${_retval:-0} ))

    # Push to server and capture the result (if upload_report.sh does not error it must print a URL)
    # We want stderr from upload_report.sh to go to stdout, so it gets plogged.
    # Note that the code relies on checking the existence of this file to see if the upload worked,
    # so if the upload fails it needs to be removed.
    rm -f "$RUN_OUTPUT"/pbpipeline/report_upload_url.txt
    if [ $_retval = 0 ] ; then
        upload_report.sh "$RUN_OUTPUT" 2>&1 >"$RUN_OUTPUT"/pbpipeline/report_upload_url.txt || \
            { log "Upload error. See $_plog" ;
              rm -f "$RUN_OUTPUT"/pbpipeline/report_upload_url.txt ; }
    fi

    send_summary_to_rt comment "$_rt_run_status" "$_rprefix Run report is at"

    # If this fails, the pipeline will continue, since only the final message to RT
    # is seen as critical.
    if [ $? != 0 ] ; then
        log "Failed to send summary to RT. See $per_run_log"
        _retval=$(( $_retval + 1 ))
    fi

    eval "$_ereset"
    # Retval will be >1 if anything failed. It's up to the caller what to do with this info.
    # The exception is for the upload. Caller should check for the URL file to see if that that failed.
    return $_retval
}

send_summary_to_rt() {
    # Sends a summary to RT. It is assumed that "$RUN_OUTPUT"/pbpipeline/report_upload_url.txt is
    # in place and can be read. In the initial cut, we'll simply list the
    # SMRT cells on the run, as I'm not sure how soon I get to see the XML meta-data?
    # Other than that, supply run_status and premble if you want this.
    _reply_or_comment="${1:-}"
    _run_status="${2:-}"
    _preamble="${3:-Run report is at}"

    # Quoting of a subject with spaces requires use of arrays but beware this:
    # https://stackoverflow.com/questions/7577052/bash-empty-array-expansion-with-set-u
    if [ -n "$_run_status" ] ; then
        _run_status=(--subject "$_run_status")
    else
        _run_status=()
    fi

    echo "Sending new summary of PacBio run to RT."
    # Subshell needed to capture STDERR from make_summary.py
    last_upload_report="`cat "$RUN_OUTPUT"/pbpipeline/report_upload_url.txt 2>/dev/null || echo "Report was not generated or upload failed"`"
    ( set +u ; rt_runticket_manager "${_run_status[@]}" --"${_reply_or_comment}" \
        @<(echo "$_preamble "$'\n'"$last_upload_report" ;
           echo ;
           make_summary.py --runid "$RUNID" --txt - \
           || echo "Error while summarizing run contents." ) ) 2>&1
}

pipeline_fail() {
    # Record a failure of the pipeline. The failure may be due to network outage so try
    # to report to RT but be prepared for that to fail too.

    stage=${1:-Pipeline}

    if [ -z "${2:-}" ] ; then
        # General failure

        # Mark the failure status
        echo "$stage on `date`" > "$RUN_OUTPUT"/pbpipeline/failed

        _failure="$stage failed"
    else
        # Failure of a cell or cells
        for c in $2 ; do
            echo "$stage on `date`" > "$RUN_OUTPUT"/pbpipeline/$c.failed
        done

        _failure="$stage failed for cells [$2]"
    fi

    # Send an alert to RT.
    # Note that after calling 'plog' we can query '$per_run_log' since all shell vars are global.
    plog "Attempting to notify error to RT"
    if rt_runticket_manager --subject failed --reply "$_failure. See log in $per_run_log" |& plog ; then
        log "FAIL $_failure on $RUNID. See $per_run_log"
    else
        # RT failure. Complain to STDERR in the hope this will generate an alert mail via CRON
        msg="FAIL $_failure on $RUNID, and also failed to report the error via RT. See $per_run_log"
        echo "$msg" >&2
        log "$msg"
    fi
}

###--->>> GET INFO FROM UPSTREAM SERVER(S) <<<---###
export UPSTREAM_LOC UPSTREAM_NAME
_upstream_info=""
_upstream_locs=""
for UPSTREAM_NAME in $UPSTREAM ; do
    eval UPSTREAM_LOC="\$UPSTREAM_${UPSTREAM_NAME}"

    _upstream_locs+="$UPSTREAM_LOC "
    _upstream_info+="$(list_remote_cells.sh)"
done

###--->>> SCANNING LOOP <<<---###

# This is more complicated than other pipelines as we have to go in stages:

# 1) Process all run directories in $PROM_RUNS
# 2) Process all new runs from $_upstream_info
# 3) Commence all syncs (see doc/syncing.sh for why this works the way it does)

log "Looking for run directories matching regex $PROM_RUNS/$RUN_NAME_REGEX/"

# If there is nothing in "$PROM_RUNS" and nothing in "$_upstream_info" it's an error.
# Seems best to be explicit checking this.
if ! compgen -G "$PROM_RUNS/*/" >/dev/null && [ -z "$_upstream_info" ] ; then
    _msg="Nothing found in $PROM_RUNS or any upstream locations (${_upstream_locs% })"
    log "$_msg"
    echo "$_msg" >&2 # This will go out as a CRON error
    exit 1
fi

# Now scan through each prom_run dir until we find something that needs dealing with.
BREAK=0
if compgen -G "$PROM_RUNS/*/" ; then for run in "$PROM_RUNS"/*/ ; do

  if ! [[ "`basename $run`" =~ ^${RUN_NAME_REGEX}$ ]] ; then
    debug "Ignoring `basename $run`"
    continue
  fi

  # invoke runinfo and collect some meta-information about the run. We're passing this info
  # to the state functions via global variables.
  # This construct allows error output to be seen in the log.
  _runstatus="$(prom_run_status.py "$run" <<<"$_upstream_info")" || \
        prom_run_status.py "$run" <<<"$_upstream_info" | log 2>&1

  # Ugly, but I can't think of a better way...
  RUNID=`grep ^RunID: <<<"$_runstatus"` ;                          RUNID=${RUNID#*: }
  INSTRUMENT=`grep ^Instrument: <<<"$_runstatus"` ;                INSTRUMENT=${INSTRUMENT#*: }
  CELLS=`grep ^Cells: <<<"$_runstatus"` ;                          CELLS=${CELLS#*: }
  CELLSREADY=`grep ^CellsReady: <<<"$_runstatus" || echo ''` ;     CELLSREADY=${CELLSREADY#*: }
  CELLSABORTED=`grep ^CellsAborted: <<<"$_runstatus" || echo ''` ; CELLSABORTED=${CELLSABORTED#*: }
  STATUS=`grep ^PipelineStatus: <<<"$_runstatus"` ;                STATUS=${STATUS#*: }

  # Resolve output location
  RUN_OUTPUT="$(readlink -f "$run/pipeline/output")"

  # FIXME - taken from SMRTino
  if [ "$STATUS" = complete ] || [ "$STATUS" = aborted ] ; then _log=debug ; else _log=log ; fi
  $_log "$run has $RUNID from $INSTRUMENT with cell(s) [$CELLS] and status=$STATUS"

  #Call the appropriate function in the appropriate directory.
  { pushd "$run" >/dev/null && eval action_"$STATUS" &&
    popd >/dev/null
  } || log "Error while trying to run action_$STATUS on $run"
  #in case this setting got clobbered...
  set -e

  # If the driver started some actual work it should request to break, as the CRON will start
  # a new scan at regular intervals in any case. We don't want an instance of the driver to
  # spend 2 hours processing then start working on a new run. On the other hand, we don't
  # want a problem run to gum up the pipeline if every instance of the script tries to process
  # it, fails, and then exits.
  # Negated test is needed to play nicely with 'set -e'
  ! [ "$BREAK" = 1 ] || break
done ; fi

if [ "$BREAK" = 1 ] ; then
    wait ; exit
fi

# Now synthesize new run events
STATUS=new
if [ -n "$UPSTREAM" ] ; then
    log "Looking for new upstream runs matching regex $RUN_NAME_REGEX"
    while read RUNID ; do
        if ! [[ "$RUNID" =~ ^${RUN_NAME_REGEX}$ ]] ; then
          debug "Ignoring $RUNID"
          continue
        fi

        if ! [ -e "$PROM_RUNS/$RUNID" ] ; then
            # FIXME - ensure these match what is emitted by run_status.py
            UPSTREAM_LOC=($(awk -F $'\t' -v runid="$RUNID" '$1 == runid {print $2}' <<<"$_upstream_info"))
            UPSTREAM_CELLS=($(awk -F $'\t' -v runid="$RUNID" '$1 == runid {print $2}' <<<"$_upstream_info"))

            { eval action_"$STATUS"
            } || log "Error while trying to run action_$STATUS on $RUNID"
        fi
    done < <(awk -F $'\t' '{print $1}' <<<"$_upstream_info")
fi

# Now start sync events. Note that due to set -eu I need to check explicitly for the empty list.
if [ -n "${SYNC_QUEUE:-}" ] ; then
    for RUNID in "${SYNC_QUEUE[@]}" ; do
        touch_atomic "$PROM_RUNS/$RUNID/pipeline/rsync.started"
        # If some calls to touch_atomic fail this will be bad. But trying to auto-recify the
        # situation could well be worse.
    done

    for RUNID in "${SYNC_QUEUE[@]}" ; do
        { pushd "$PROM_RUNS/$RUNID" >/dev/null && eval do_rsync &&
          popd >/dev/null
        } || log "Error while trying to run Rsync on $PROM_RUNS/$RUNID"
    done
fi

wait
