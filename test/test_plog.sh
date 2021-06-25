#!/bin/bash

# Messing around with some shell functions
exec 5>&1

plog() {
    if [ -z "${per_run_log:-}" ] ; then
        per_run_log="log_test.out"
        # In SPEW mode, log to the terminal too
        if [ "${SPEW:-0}" != 0 ] ; then
            exec 6> >(tee -a "$per_run_log" >&5)
        else
            exec 6>>"$per_run_log"
        fi
    fi
    if ! { [ $# = 0 ] && cat >&6 || echo "$@" >&6 ; } ; then
       log '!!'" Failed to write to $per_run_log"
       log "$@"
    fi
}

plog "Hello world"
date | plog

##
tail -v -n+0 "$per_run_log"
