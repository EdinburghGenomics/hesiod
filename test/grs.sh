#!/bin/bash
IFS=$'\t'

# This script is about me tinkering with better ways to dissect the output of run_status.py
# and get_remote_cells.sh in the shell. It's not part of the unit tests.

export UPSTREAM_LOC=test/examples/upstream2
export UPSTREAM_NAME=TEST
UPSTREAM_INFO="$(./list_remote_cells.sh)"

log(){
    cat
}

# I was doing it like this before:
get_run_status_old() { # run_dir
  # invoke run_status.py in CWD and collect some meta-information about the run.
  # We're passing this info to the state functions via global variables.

  # This construct allows error output to be seen in the log.
  _runstatus="$(./run_status.py "$1" <<<"$UPSTREAM_INFO")" || \
        ./run_status.py "$1" <<<"$UPSTREAM_INFO" | log 2>&1

  # Ugly, but I can't think of a better way...
  RUNID=`grep ^RunID: <<<"$_runstatus"` ;                          RUNID=${RUNID#*: }
  INSTRUMENT=`grep ^Instrument: <<<"$_runstatus"` ;                INSTRUMENT=${INSTRUMENT#*: }
  CELLS=`grep ^Cells: <<<"$_runstatus"` ;                          CELLS=(${CELLS#*: })
  CELLSPENDING=`grep ^CellsPending: <<<"$_runstatus"` ;            CELLSPENDING=(${CELLSPENDING#*: })
  CELLSREADY=`grep ^CellsReady: <<<"$_runstatus" || echo ''` ;     CELLSREADY=${CELLSREADY#*: }
  CELLSABORTED=`grep ^CellsAborted: <<<"$_runstatus" || echo ''` ; CELLSABORTED=${CELLSABORTED#*: }
  STATUS=`grep ^PipelineStatus: <<<"$_runstatus"` ;                STATUS=${STATUS#*: }
  UPSTREAM=`grep ^Upstream: <<<"$_runstatus"` ;                    UPSTREAM=${UPSTREAM#*: }

  # Resolve output location
  RUN_OUTPUT="$(readlink -f "$run/pipeline/output" || true)"
}

# But how about this, with many backslashes...
get_run_status_eval() { # run_dir
  # invoke run_status.py in CWD and collect some meta-information about the run.
  # We're passing this info to the state functions via global variables.

  # This construct allows error output to be seen in the log.
  _runstatus="$(./run_status.py "$1" <<<"$UPSTREAM_INFO")" || \
        ./run_status.py "$1" <<<"$UPSTREAM_INFO" | log 2>&1

  for _v in RUNID/RunID INSTRUMENT/Instrument \
            CELLS/Cells CELLSPENDING/CellsPending CELLSREADY/CellsReady CELLSABORTED/CellsAborted \
            STATUS/PipelineStatus UPSTREAM/Upstream ; do
    eval "${_v%/*}=\`grep ^${_v#*/}: <<<\"\$_runstatus\"\`" ; eval "${_v%/*}=\${${_v%/*}#*: }"
  done

  # Resolve output location
  RUN_OUTPUT="$(readlink -f "$run/pipeline/output" || true)"
}

# Or this mildly saner version
get_run_status() { # run_dir
  # invoke run_status.py in CWD and collect some meta-information about the run.
  # We're passing this info to the state functions via global variables.

  # This construct allows error output to be seen in the log.
  _runstatus="$(./run_status.py "$1" <<<"$UPSTREAM_INFO")" || \
        ./run_status.py "$1" <<<"$UPSTREAM_INFO" | log 2>&1

  for _v in RUNID/RunID INSTRUMENT/Instrument \
            CELLS/Cells CELLSPENDING/CellsPending CELLSREADY/CellsReady CELLSABORTED/CellsAborted \
            STATUS/PipelineStatus UPSTREAM/Upstream ; do

    _line="$(awk -v FS=":" -v f="${_v#*/}" '$1==f {gsub(/^[^:]*:[[:space:]]*/,"");print}' <<<"$_runstatus")"
    #eval "${_v%/*}"='"$_line"'
    IFS=$'\t' read -a "${_v%/*}" <<<"$_line" 
  done

  # Resolve output location
  RUN_OUTPUT="$(readlink -f "$run/pipeline/output" || true)"
}

get_run_status test/examples/runs/20000101_TEST_00testrun2/

cat -A <<<"$RUNID"
cat -A <<<"$STATUS"
cat -A <<<"$UPSTREAM"
cat -A <<<"${CELLS[@]}"
cat -A <<<"$CELLSABORTED"
