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
import logging
import gzip
from io import BytesIO
import shutil
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter

def glob():
    """Regular glob() is useful but we want consistent sort order."""
    from glob import glob
    return lambda p: sorted( (f.rstrip('/') for f in glob(os.path.expanduser(p))) )
glob = glob()

import pysam
from tqdm import tqdm
import pandas as pd
import numpy as np
import h5py

def main(args):
    # Open the BAM file for reading
    bamfile, = args.bamfile

    logging.basicConfig( level = logging.INFO,
                         format = "{levelname}:{message}",
                         style = '{')

    # For debugging
    start_time = time()

    seqs_in_bam = seqs_from_stats(args.stats)

    with pysam.AlignmentFile(bamfile, "rb") as samfh:

        # Yes I could use the logging module here
        logging.info( "Opened {} for reading.".format(os.path.basename(bamfile)) )

        df = sam_to_df(samfh, total=seqs_in_bam)

    # Now load the .fast5 infos. Add columns to df to collect the
    # start times etc. as float values (in seconds)
    df['StartTime']  = 0.0
    df['Duration']   = 0.0

    if args.seq_summary:
        logging.info("Getting values from '{}'".format(args.seq_summary) )

        collect_from_seqsum(args.seq_summary, df)

    elif args.fast5:
        logging.info("Scanning .fast5.gz files in '{}'".format(args.fast5) )

        collect_from_fast5(glob(os.path.join(args.fast5, '*.fast5.gz')), df)

    else:
        # Should be impossible as default is to scan for fast5 files in CWD.
        exit("No fast5 or summary info provided")

    logging.info( "DONE" )

    time_taken = int(time() - start_time)
    logging.info( "There are {} records loaded in {} seconds.".format(len(df), time_taken) )

    print(df)

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

def collect_from_seqsum(seqsum_file, df):
    """Read from the sequencing summary file and add to the data frame provided.
    """
    # Establish the columns in the data frame, since I plan to use ds.iat to
    # set things by position (which should be fast).
    assert list(df)[2:4] == ['StartTime', 'Duration']

    header_map = dict()
    pbar = tqdm(total=len(df))

    def _collect(fh):
        # Extract info from lines in fh
        for aline in fh:

            lparts = aline.rstrip().split('\t')
            ri = lparts[header_map['read_id']]

            if ri in df.index:
                # Write into the data frame.
                loc = df.index.get_loc(ri)
                df.iat[loc, 2] = float(lparts[header_map['start_time']])
                df.iat[loc, 3] = float(lparts[header_map['duration']])

                pbar.update()

    _open = gzip.open if seqsum_file.endswith('.gz') else open
    with _open(seqsum_file, 'rt') as fh:
        for n, h in enumerate(next(fh).rstrip().split('\t')):
            header_map[h] = n

        _collect(fh)

    pbar.close()

def collect_from_fast5(f5_list, df):
    """Read from the list of fast5 files and add to the data frame provided.
       Note that adding values one-at-a-time to a Pandas data frame is supposed to
       be an anti-pattern but I can't see a better way to do it just now, and
       most of the time is spent reading the fast5 anyway.
    """
    # Establish the columns in the data frame, since I plan to use ds.iat to
    # set things by position (which should be fast).
    assert list(df)[2:4] == ['StartTime', 'Duration']

    pbar = tqdm(total=len(df))

    def _collect(f5):
        """Internal function to add info from one f5 file to the dataframe.
        """
        for read_group in f5:

            read_attrs = read_group['Raw'].attrs
            ri = read_attrs['read_id'].decode()

            # This test is slightly faster then catching the exaception if most entries
            # are not in the index (which is the case here).
            if ri in df.index:
                # Check out the sampling rate (which should be the same for all reads??)
                srate = read_group['channel_id'].attrs['sampling_rate']

                # Write into the data frame.
                loc = df.index.get_loc(ri)
                df.iat[loc, 2] = read_attrs['start_time'] / srate
                df.iat[loc, 3] = read_attrs['duration'] / srate

                pbar.update()

    for f5_file in f5_list:

        if f5_file.endswith('.gz'):
            # Unpack the entire file in memory - much faster than a direct read from gzip handle
            with BytesIO() as bfh:
                with gzip.open(f5_file, 'rb') as zfh:
                    shutil.copyfileobj(zfh, bfh)
                bfh.seek(0)

                _collect(info_from_fast5(bfh))
        else:
            # Let h5py open the file directly
            _collect(info_from_fast5(f5_file))

    pbar.close()

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
    with tqdm(total=total) as pbar:
        for read in sf.fetch(until_eof=True):

            # Always ignore unmapped reads - though we shouldn't see any
            # We do see some supplementary (ie. split) mappings, which I'm just going to ignore
            # here.
            if read.flag & (pysam.FUNMAP | pysam.FSECONDARY | pysam.FSUPPLEMENTARY):
                continue

            # Either we have the Alignment Score or we need to calculate it
            # from the CIGAR string.
            # Note for minimap2 I don't actually know how the AS is calculated so I'll
            # ignore it! - see https://www.biostars.org/p/409568/
            """
            try:
                ascore = read.get_tag('AS')
            except KeyError:
                ...
            """
            # See https://pysam.readthedocs.io/en/latest/api.html#pysam.AlignedSegment.cigartuples
            ascore = sum( t[1] for t in read.cigartuples if t[0] == 0 )

            # Add to the lists
            read_ids.append(read.query_name)
            rl = read.query_length # could use read.infer_read_length()?
            alignment_scores.append(ascore)
            read_lengths.append(rl)

            # Print progress
            pbar.update()

    # And here's your result, as a Pandas thingy, with the read ID as the index
    logging.info( "Generating dataframe with {} rows.".format(len(read_ids)) )
    return pd.DataFrame( { 'AlignmentScore' : alignment_scores,
                           'ReadLength' : read_lengths,
                         },
                         index = read_ids )

def info_from_fast5(fobj):
    """Returns a list of infos from a fast5 file.
       I'd assumed I could do this using ont_fast5_api but for various reasons it seems
       far simpler to code it myself. However I have looked at code from
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

        # Since I realised I need v['Raw'].attrs and also v['channel_id'].attrs
        # just do this.
        yield from handle.values()

def parse_args(*args):
    description = """Plots alignment scores in BAM over time"""

    parser = ArgumentParser( description = description,
                             formatter_class = ArgumentDefaultsHelpFormatter)

    parser.add_argument("-f", "--fast5", default='.',
                        help="Directory to scan for .fast5[.gz] files")
    parser.add_argument("-q", "--seq_summary",
                        help="File to read for sequence summary info (rather than fast5)")
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

