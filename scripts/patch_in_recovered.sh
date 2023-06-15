#!/bin/bash
set -eou pipefail
shopt -s nullglob

## If live basecalling does not complete, we have to re-run it as an analysis
## and deliver the results.
## But the output from the basecalling analysis is arranged differently to what we
## see from live basecalling and is no good for Hesiod. This script attempts
## to make it work.
##
## You need the original cell data directory with the new basecalling in ./basecalling
## and this script will patch everything up.

RECALL_DATA="./basecalling"

die(){ echo "$@" ; exit 1 ; }

for d in basecalling fast5_pass fast5_fail ; do
    test -d "$d" || die "No such directory ./$d"
done

echo "Checking for new basecalling in ${RECALL_DATA}..."
n_seq_summ=(${RECALL_DATA}/[s]equencing_summary.txt)
if [[ "${#n_seq_summ[@]}" != 1 ]] ; then
    die "Did not find ${RECALL_DATA}/sequencing_summary.txt file."
fi
if [ ! -e "${RECALL_DATA}/pass" ] || [ ! -e "${RECALL_DATA}/fail" ] ; then
    die "Missing pass and fail in ${RECALL_DATA}"
fi
echo OK

# Get the run_id from the first line of sequencing_summary.txt
get_run_id(){
    awk 'NR==1{for(i=1;i<=NF;i++){ix[$i]=i}};NR>1{print $ix["run_id"];exit 0}' "$1"
}
n_run_id=$(get_run_id "$n_seq_summ")

echo "Run is $n_run_id"

echo "Moving old fastq and bam directories"
# This will abort if the dir exists
mkdir original_fastq_and_bam
mv -t original_fastq_and_bam {bam,fastq}_{pass,fail}

echo "Linking in the new sequencing summary"
cp -vl -t . "$n_seq_summ"

echo "Hard-linking pass and fail FASTQ and BAM from ${RECALL_DATA}"
for ftype in fastq bam ; do
for pf in pass fail ; do
    mkdir ${ftype}_${pf}

    subdirs=("$RECALL_DATA"/"$pf"/*/)
    if [[ "${#subdirs[@]}" > 0 ]] ; then
        # We got barcodes
        for s in "${subdirs[@]}" ; do
            s=$(basename "$s")
            mkdir -v ${ftype}_${pf}/"$s"
            cp -vl -t ${ftype}_${pf}/"$s" "$RECALL_DATA"/"$pf"/"$s"/*${ftype} "$RECALL_DATA"/"$pf"/"$s"/*${ftype}.gz
        done
    else
        # No barcodes. Easier.
        cp -vl -t ${ftype}_${pf} "$RECALL_DATA"/"$pf"/*.${ftype} "$RECALL_DATA"/"$pf"/*.${ftype}.gz
    fi
done
done

p_fin_summ=final_summary_basecall_recovery.txt
echo "Fixing the final summary ($p_fin_summ)"

fastq_count=$(find "$RECALL_DATA" -type f '(' -name '*.fastq' -or -name '*.fastq.gz' ')' | wc -l)
fast5_count=$(find fast5_* -type f | wc -l)

echo "# Added by `realpath $0`" >> "$p_fin_summ"
echo "sequencing_summary_file=sequencing_summary.txt" >> "$p_fin_summ"
echo "fastq_files_in_final_dest=$fastq_count" >> "$p_fin_summ"
echo "fast5_files_in_final_dest=$fast5_count" >> "$p_fin_summ"

echo "DONE"

echo "For now, you also need to manually add some stuff to ${p_fin_summ}"
