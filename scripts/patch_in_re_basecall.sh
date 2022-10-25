#!/bin/bash
set -eou pipefail
shopt -s nullglob

## If a run has been re-basecalled in MinKNOW, as opposed to using live basecalling, then
## we might want to push it through Hesiod and deliver the results.
## But the output from the basecalling analysis is no good for Hesiod. This script attempts
## to make it work.
##
## You need the original cell data directory and the re-basecalled directory.
## The default output will be <celldir>.recall00

ORIGINAL_CELL="${1%%/}"
RECALL_DATA="${2%%/}"
OUT_DIR="${3:-$ORIGINAL_CELL.recall00}"

die(){ echo "$@" ; exit 1 ; }

# Get the run_id from the first line of sequencing_summary.txt
get_run_id(){
    awk 'NR==1{for(i=1;i<=NF;i++){ix[$i]=i}};NR>1{print $ix["run_id"];exit 0}' "$1"
}

# Check that the directories contain what we expect.
echo "Checking for an original cell in $ORIGINAL_CELL..."
o_fin_summ=("$ORIGINAL_CELL"/final_summary_*_*.txt)
if [[ "${#o_fin_summ[@]}" != 1 ]] ; then
    die "Did not find one final_summary_*_*.txt file in $ORIGINAL_CELL. Found ${#o_fin_summ[@]}."
fi
o_seq_summ=("$ORIGINAL_CELL"/sequencing_summary_*_*.txt)
if [[ "${#o_seq_summ[@]}" != 1 ]] ; then
    die "Did not find one sequencing_summary_*_*.txt file in $ORIGINAL_CELL. Found ${#o_seq_summ[@]}."
fi

echo "Checking for new basecalling in $RECALL_DATA..."
n_seq_summ=("$RECALL_DATA"/[s]equencing_summary.txt)
if [[ "${#n_seq_summ[@]}" != 1 ]] ; then
    die "Did not find sequencing_summary.txt file in $RECALL_DATA."
fi
if [ ! -e "$RECALL_DATA"/pass ] || [ ! -e "$RECALL_DATA"/fail ] ; then
    die "Missing pass and fail in $RECALL_DATA"
fi
echo OK

# We want some form of check that these are really the same reads.
echo "Checking that the run_id matches..."
o_run_id=$(get_run_id "$o_seq_summ")
n_run_id=$(get_run_id "$n_seq_summ")
[ -n "$o_run_id" ] || die "Failed to get run_id from $o_seq_summ"
[[ "$o_run_id" == "$n_run_id" ]] || die "Mismatched run_id: $o_run_id != $n_run_id"
echo "OK - $o_run_id"

# The output dir should be new, and in an existing directory. Empty dir is OK
[ ! -e "$OUT_DIR" ] || rmdir -v "$OUT_DIR"
mkdir -v "$OUT_DIR"

# We'll use a link to avoid copying the data
echo "Linking in the new sequencing summary"
cp -vl -t "$OUT_DIR" "$n_seq_summ"
# But this needs to be modified so we copy it
echo "Copying in the original final summary"
cp -v -t "$OUT_DIR" "$o_fin_summ"

echo "Symlinking the directories of the original fast5 files"
for x in pass fail skip ; do
    if [ -e "$ORIGINAL_CELL"/fast5_${x} ] ; then
        ln -vsnrf -t "$OUT_DIR" "$ORIGINAL_CELL"/fast5_${x}
    fi
done

echo "Hard-linking pass and fail FASTQ from $RECALL_DATA"
for x in pass fail ; do
    mkdir "$OUT_DIR"/fastq_${x}

    subdirs=("$RECALL_DATA"/"$x"/*/)
    if [[ "${#subdirs[@]}" > 0 ]] ; then
        # We got barcodes
        for s in "${subdirs[@]}" ; do
            s=$(basename "$s")
            mkdir -v "$OUT_DIR"/fastq_${x}/"$s"
            cp -vl -t "$OUT_DIR"/fastq_${x}/"$s" "$RECALL_DATA"/"$x"/"$s"/*
        done
    else
        # No barcodes. Easier.
        cp -vl -t "$OUT_DIR"/fastq_${x} "$RECALL_DATA"/"$x"/*
    fi
done

p_fin_summ="$OUT_DIR"/$(basename "$o_fin_summ")
echo "Fixing the final summary ($p_fin_summ)"

fastq_count=$(find "$RECALL_DATA" -type f '(' -name '*.fastq' -or -name '*.fastq.gz' ')' | wc -l)

echo "# Added by hesiod/scripts/patch_in_re_basecall.sh" >> "$p_fin_summ"
echo "sequencing_summary_file=sequencing_summary.txt" >> "$p_fin_summ"
echo "fastq_files_in_final_dest=$fastq_count" >> "$p_fin_summ"


echo "DONE"
