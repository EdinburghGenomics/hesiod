#!/usr/bin/env python3

"""Given a BAM file aligned to lambda and the original fast5 files,
   extract and plot identity scores by time.
   Inputs:
    One BAM file (will be ready via PySAM)
    A directory where .fast5 files may be found
    ( the start time of the run - or is this in the fast5?? )
"""

import os, sys, re
from time import time, sleep
from glob import glob
import logging
import gzip
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter

import pysam
from tqdm import tqdm
import pandas as pd
import numpy as np
import h5py

def main(args):
    # Open the BAM file for reading
    bamfile, = args.bamfile

    # For debugging
    start_time = time()

    seqs_in_bam = seqs_from_stats(args.stats)

    with pysam.AlignmentFile(bamfile, "rb") as samfh:

        # Yes I could use the logging module here
        print( "Opened {} for reading.".format(bamfile), file=sys.stderr )

        df = sam_to_df(samfh, total=seqs_in_bam)

    # Now load the .fast5 infos. Add columns to df to collect the
    # start times etc. as int64 values
    # FIXME - set the DTYPE as per the HDF5
    df['StartTime']  = 0
    df['Duration']   = 0

    for f5_file in tqdm(glob(os.path.join(args.fast5, '*.fast5.gz'))):
        collect_from_fast5(info_from_fast5(gzip.open(f5_file)), df)

    print( "DONE", file=sys.stderr )

    time_taken = int(time() - start_time)
    print( "There are {} records loaded in {} seconds.".format(len(df), time_taken) )

def seqs_from_stats(statfile):
    """Looks in the specified file for a line "SN    sequences:  {\d+}" and
       returns the number. If the file is not found or the line is not found
       returns None.
    """
    try:
        with open(statfile) as sfh:
            for line in sfh:
                mo = re.match(r'SN\s+sequences:\s+(\d+)', line)
                if mo:
                    return int(mo.group(1))
    except (FileNotFoundError, TypeError):
        return None

    # Or if we hit the end of the file with no match, also
    return None

def collect_from_fast5(f5, df):
    """Read from the iterator in f5 and add to the data frame provided.
       Note that adding values one-at-a-time to a Pandas data frame is supposed to
       be an anti-pattern but I can't see a better way to do it just now.
    """
    # Establish the columns in the data frame, since I plan to use ds.iat to
    # set things by position (which should be fast).
    assert list(df)[2:4] == ['StartTime', 'Duration']

    # TODO - tqdm here or not?
    for read_attrs in f5:

        # Does this test work?? Should I get the index at the same time??
        try:
            loc = df.index.get_loc(read_attrs['read_id'].decode())
        except KeyError:
            continue

        # FIXME - Handling an exception per read can't be efficient?!
        # Maybe I should check explicitly??
        #if ri.read_id not in df.index:
        #    import pdb ; pdb.set_trace()

        df.iat[loc, 2] = read_attrs['start_time']
        df.iat[loc, 3] = read_attrs['duration']


def sam_to_df(sf, total = None):
    """ Reads form an open AlignmentFile object and returns a Pandas DataFrame with
        ReadID as the index and AlignmentScore columns.
    """

    # It seems that trying to add rows dynamically to a Pandas dataframe is strongly
    # discouraged, so I guess I need to make two lists?
    read_ids = list()
    alignment_scores = list()
    read_lengths = list()

    # FIXME - progress needs to be switch-offable
    # FIXME2 - could get the number of reads from the stats file.
    for read in tqdm(sf.fetch(until_eof=True), total=total):

        # Always ignore unmapped reads - though we shouldn't see any
        if read.is_unmapped:
            pass

        sleep(1)

        # Either we have the Alignment Score or we need to calculate it
        # from the CIGAR string.
        try:
            ascore = read.get_tag('AS')
        except KeyError:
            # See https://pysam.readthedocs.io/en/latest/api.html#pysam.AlignedSegment.cigartuples
            ascore = sum( t[1] for t in read.cigartuples if t[0] == 0 )

        # Add to the lists
        read_ids.append(read.query_name)
        rl = read.query_length # could use read.infer_read_length()?
        alignment_scores.append( ( ascore ) / rl )
        read_lengths.append(rl)

    # And here's your result, as a Pandas thingy, with the read ID as the index
    print( "Generating dataframe with {} rows.".format(len(read_ids)), file=sys.stderr )
    return pd.DataFrame( { 'AlignmentScore' : alignment_scores,
                           'ReadLength' : read_lengths,
                         },
                         index = read_ids )

def info_from_fast5(fobj):
    """Returns a list of infos from a fast5 file.
       I'd assumed I could do this using ont_fast5_api but for various reasons it seems
       far simpler to code it myself. However I have used code from
       https://github.com/nanoporetech/ont_fast5_api/blob/master/ont_fast5_api/fast5_info.py
       as a starting point.
    """
    # TODO - see if I'd be better getting this from the summary file??

    with h5py.File(fobj, 'r') as handle:

        # Version check!? In development the files are '1.0'
        # so maybe I should check for this?
        try:
            assert handle.attrs['file_version'] == b'1.0'
        except Exception:
            logging.exception("Version check failed")

        # We need all the items matching Raw/Reads/{}. In the sample code we get
        # for read in handle['Raw/Reads'].keys():
        #   read_group = handle['Raw/Reads/{}'.format(read)]

        # But I think we can just do this?
        for v in handle.values():
            yield v['Raw'].attrs

def parse_args(*args):
    description = """Plots alignment scores in BAM over time"""

    parser = ArgumentParser( description = description,
                             formatter_class = ArgumentDefaultsHelpFormatter)

    parser.add_argument("-f", "--fast5", default='.',
                        help="Directory to scan for .fast5[.gz] files")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Print progress to stderr")
    parser.add_argument("-s", "--stats",
                        help="Stats file for the BAM. Optionally used to set the progress bar with the"
                             " correct number of sequences.")
    parser.add_argument("bamfile", nargs=1,
                        help="The BAM file to be read")

    return parser.parse_args(*args)

if __name__=="__main__":
    main(parse_args())

