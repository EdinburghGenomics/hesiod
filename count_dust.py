#!/usr/bin/env python3
import sys

# Read the output of dustmasker_static and report the proportion of
# non-dust (uppercase) per sequence.
upper = 0
lower = 0
count = 0
# These aren't contigs but we pretend they are...
contig = None

# This just prints out the proportion, which is the more sensible
# type of output.
"""
def emit():
    if count:
        total = upper + lower
        print('0.000' if total == 0 else "{:.3f}".format(upper / total))
"""

# But for blobtools we want something a little different.
print("## count_dust v0.0")
print("## Total Reads = 10000") # We assume?!
print("## Mapped Reads = 10000")
print("## Unmapped Reads = 0")
print("# contig_id\tread_cov\tbase_cov")
def emit():
    if count:
        total = upper + lower
        frac = 0.0 if total == 0 else (upper / total)
        # With vanilla blobtools you need to cram the values into the log scale
        # print("{}\t1\t{:.3f}".format(contig, 10**(5*(frac-0.5))))
        # With the patched version you can avoid this.
        print("{}\t1\t{:.3f}".format(contig, frac))

for l in sys.stdin:
    if l.startswith('>'):
        emit()
        count += 1
        contig = l.split('|')[1].strip()
        upper = lower = 0
    else:
        upper += sum( 1 for n in l if n in 'ATCG' )
        lower += sum( 1 for n in l if n in 'atcg' )
emit()
