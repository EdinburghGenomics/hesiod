# Config parameters for Hesiod
STALL_TIME=''

UPSTREAM=prom@promethion:/data
PROM_RUNS=/lustre/promethion/prom_runs
FASTQDATA=/lustre/promethion/prom_fastqdata

# I suspect this is not what I want in the config but...
SYNC_CMD="rsync -vrlptDR ${UPSTREAM}/{remote_run}/./{lib}/{flowcell} ${PROM_RUNS}/{local_run}/"
## Or:
SYNC_CMD="ssh ${UPSTREAM%%:*} rsync -vrlptDR ${UPSTREAM#*:}/{remote_run}/./{lib}/{flowcell} /mnt/lustre/prometion/prom_runs/{local_run}/"

