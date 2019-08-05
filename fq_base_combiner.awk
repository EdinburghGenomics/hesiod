#!/usr/bin/gawk -f

# Combine outputs of of fq_base_counter.py in AWK.
# Note we do not have "awk -M" available but this should still allow us
# to count up to 2^53 bases (9 petabases)

BEGIN{
    non_n_bases = 0
    total_reads = 0
    total_bases = 0
    min_len = 0
    max_len = 0
    if(!fn) fn="unknown"
}

{
    if($1 == "total_reads:"){ total_reads += $2 }
    if($1 == "total_bases:"){ total_bases += $2 }
    if($1 == "non_n_bases:"){ non_n_bases += $2 }
    if($1 == "read_length:"){
        split($2, rl, "-")
        if(rl[length(rl)] > max_len){ max_len = rl[length(rl)] }
        if(min_len == 0 || rl[1] < min_len){ min_len = rl[1] }
    }

}
END {
    print "filename:    "fn
    print "total_reads: "total_reads
    print "read_length: "min_len"-"max_len
    print "total_bases: "total_bases
    print "non_n_bases: "non_n_bases
}
