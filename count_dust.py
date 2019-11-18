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
res = []
def emit():
    if count:
        total = upper + lower
        frac = 0.0 if total == 0 else (upper / total)
        # With vanilla blobtools you need to cram the values into the log scale
        # print("{}\t1\t{:.3f}".format(contig, 10**(5*(frac-0.5))))
        # With the patched version you can avoid this.
        res.append("{}\t1\t{:.3f}".format(contig, frac))

def print_result():
    """Prints out the lines in res. Previously I printed them as I read the file but now
       I need the total number to go into the header.
    """
    assert count == len(res)

    print("## count_dust v0.1")
    print("## Total Reads = {}".format(count))
    print("## Mapped Reads = {}".format(count))
    print("## Unmapped Reads = 0")
    print("# contig_id\tread_cov\tbase_cov")

    for l in res:
        print(l)

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
print_result()
