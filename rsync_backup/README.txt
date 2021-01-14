At some point we'll start doing backups to the tape library at ACF.

But for now we have FluidFS. I'll back up everything to there the same way we do with Illumina.

I'll exclude the .snakemake and slurm_output directories as these are full of pointless small
files, but I'll keep the other logs etc.

I'll only sync runs that are in status 'complete'. This means I need to be able to run the
run_status.py script to check that. Therefore it makes sense for the backup script to be in with
the Hesiod code, so that is where you'll find it, along with an up-to-date version of
this file under rsync_backup/.

I can handle my log redirection with cron_o_matic. Also if I'm only working on recent runs I can
maybe venture to use the --delete flag on RSYNC. Is that ever safe???

See the script for further comments. Note the script is adapted from the one in Illuminatus.
