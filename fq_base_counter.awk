#!/usr/bin/gawk -f

# Reimplementation of fq_base_counter.py in AWK for max speed
# Note we do not have "awk -M" available but this should still allow us
# to count up to 2^53 bases (9 petabases)

BEGIN{
    FS="\0"
    non_n_bases = 0
    total_bases = 0
    min_len = 0
    max_len = 0
    if(!fn) fn="unknown"
}

{
    if((NR%4)==2){
        total_bases += length
        if(length > max_len) max_len = length
        if(min_len == 0 || length < min_len) min_len = length
        gsub("[N]", "")
        non_n_bases += length
    }

}
END {
    print "filename:    "fn
    print "total_reads: "NR/4
    print "read_length: "min_len"-"max_len
    print "total_bases: "total_bases
    print "non_n_bases: "non_n_bases
}
