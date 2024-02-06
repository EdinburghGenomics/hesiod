#!/bin/bash
set -euo pipefail
shopt -s nullglob

# Allow VERBOSE to override the environ.sh setting
_verbose="${VERBOSE:-}"

# Load the settings for this pipeline.
HESIOD_HOME="$(readlink -f $(dirname $BASH_SOURCE)/..)"
ENVIRON_SH="${ENVIRON_SH:-$HESIOD_HOME/environ.sh}"
if [ -e "$ENVIRON_SH" ] ; then
    pushd "`dirname $ENVIRON_SH`" >/dev/null
    source "`basename $ENVIRON_SH`"
    popd >/dev/null

    export FASTQDATA RUN_NAME_REGEX VERBOSE \
           BACKUP_DRY_RUN BACKUP_LOCATION BACKUP_NAME_REGEX BACKUP_FAST5
fi

# Add the PATH
export PATH="$HESIOD_HOME:$PATH"
export VERBOSE="${_verbose:-${VERBOSE:-0}}"

# Optional echo
debug(){ if [ "${VERBOSE}" != 0 ] ; then echo "$@" ; fi ; }

# The config file must provide FASTQDATA and BACKUP_LOCATION, assuming they
# were not already set in the environment. To explicitly ignore the environ.sh
# do something like:
# $ env ENVIRON_SH=/dev/null FASTQDATA=foo BACKUP_LOCATION=bar sync_to_backup_location.sh

# Where are runs coming from?
# Where are runs going to (can be a local directory or host:/path)?
echo "Backing up Promethion data from $FASTQDATA to $BACKUP_LOCATION"

# We can supply a BACKUP_NAME_REGEX or fall back to RUN_NAME_REGEX (the default here
# should match the one hard-coded in driver.sh)
RUN_NAME_REGEX="${RUN_NAME_REGEX:-.*_.*_.*_}"
BACKUP_NAME_REGEX="${BACKUP_NAME_REGEX:-$RUN_NAME_REGEX}"
debug "BACKUP_NAME_REGEX=$BACKUP_NAME_REGEX"
echo ===

# Now loop through all the projects in a similar manner to the driver and the state reporter.
# But note we loop through $FASTQDATA_LOCATION not $SEQDATA_LOCATION.
for run in "$FASTQDATA"/*/ ; do

  debug "Considering $run"

  # This also lops the trailing /, but we rely on $run still having one.
  run_name="$(basename $run)"

  # Apply filter
  if ! [[ "$run_name" =~ ^${BACKUP_NAME_REGEX}$ ]] ; then
    debug "Ignoring directory $run_name which does not match regex"
    continue
  fi

  # Invoke run_status.py to see if the run is done. Same as in
  # deletion_management_tools/find_prom_runs_to_delete.sh
  run_status=$(run_status.py "$run" | sed -n '/^PipelineStatus:/s/.*: *//p')
  debug "Status is reported as $run_status"

  # Wait for qc to complete before running the sync.
  # Maybe I should RSYNC anyway here and not wait for final QC? But that gets messy.
  # If the pipeline dir is missing this check will be skipped, but we do need the log - see the next check.
  if [ "$run_status" != "complete" ] ; then
    debug "Ignoring $run_status $run_name"
    continue
  fi

  # If the pipeline.log is missing we have problems
  if [ ! -e "$run/pipeline.log" ] ; then
    echo "Missing $run/pipeline.log - something is wrong here! Run will not be copied!"
    continue
  fi

  # Comparing times on pipeline.log is probably the simplest way to see if the copy
  # is up-to-date and saves my sync-ing everything again and again
  # Note this will also trigger if the run directory itself has changed (perms or mtime)
  if rsync -ns -rlptD --itemize-changes --include='pipeline.log' --exclude='*' "$run" "$BACKUP_LOCATION/$run_name" | grep -q . ; then
    log_size=`stat -c %s "$run/pipeline.log"`
    echo "Detected activity for $run_name with log size $log_size"
  else
    debug "No recent pipeline activity for $run_name"
    continue
  fi

  # === OK, here we go with the actual sync... ===
  echo "*** Starting sync for $run_name ***"

  if [ "${BACKUP_DRY_RUN:-0}" != 0 ] ; then
    echo "*** DRY_RUN - skipping ***"
    continue
  fi

  if [ "${VERBOSE}" != 0 ] ; then set -x ; fi

  excludes=(--exclude='**/.snakemake' --exclude='**/slurm_output')
  if [ "${BACKUP_FAST5:-yes}" = no ] ; then
    excludes+=(--exclude='*.fast5' --exclude='*.fast5.gz' --exclude='*.pod5')
  fi

  # Note there is no --delete flag so if the sample list changes the old files will remain on the backup.
  # This should not be a problem. If --delete is added below then the --backup flag should prevent cascading data
  # loss in the case where files are accidentally removed from the master copy.
  # Since --backup implies --omit-dir-times we have to do a special fix for that, or else the test for activity gets
  # triggered again and again.
  rsync -rlpt -sbv "${excludes[@]}" --exclude={rundata,projects_deleted.txt,pipeline.log} \
    "$run" "$BACKUP_LOCATION/$run_name"
  rsync -svrt --exclude='**' \
    "$run" "$BACKUP_LOCATION/$run_name"

  # Just to test the log catcher below we can...
  # echo BUMP >> "$run/pipeline.log"

  # Now add the pipeline directory from the rundata dir (if it still exists)
  [ ! -e "$run"/rundata/ ] || \
  rsync -sbav --del --exclude='pipeline/output' --include='pipeline**' --exclude='*' \
    "$run"rundata/ "$BACKUP_LOCATION/$run_name/rundata"

  # And finally the log. Do this last so if copying was interrupted/incomplete it will be obvious.
  # If the log has changed at all during the copy process it's not a problem, because this
  # step will alter the mtime of the directory and trigger a second sync.
  # (I actually discovered this as a bug, but it turns out to be a handy feature!)
  rsync -sa --itemize-changes "$run/pipeline.log" "$BACKUP_LOCATION/$run_name/pipeline.log"
  set +x
  if [ `stat -c %s "$run/pipeline.log"` != $log_size ] ; then
    echo "Log file size has changed during sync. However this should not be a problem as a second"
    echo "sync is going to be triggered."
  fi

  echo "*** Copied FASTQ data and pipeline metadata for $run_name ***"
done
