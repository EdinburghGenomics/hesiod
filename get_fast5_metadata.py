#!/usr/bin/env python3

"""Given a directory of .fast5 files, extract some metadata:
    1) Version of the .fast5 files
    2) Start time of the run
    3) Version of Guppy (or other basecaller)
   Inputs:
    A directory where .fast5 files may be found
"""

import os, sys, re
import logging
import gzip
from io import BytesIO
import shutil
import math
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from collections import OrderedDict

# For reading teh fast5...
import h5py
# For data handling and plotting
import numpy as np

from hesiod import dump_yaml, glob

def main(args):

    logging.basicConfig( level = logging.DEBUG if args.verbose else logging.INFO,
                         format = "{levelname}:{message}",
                         style = '{')

    logging.debug("Scanning .fast5.gz files in '{}'".format(args.fast5) )
    md = md_from_fast5_dir(args.fast5)

    print(dump_yaml(md))

def md_from_fast5_dir(f5_dir):
    """Read from the directory of fast5 files and return a dict of metadata.
    """
    f5_files = glob(os.path.join(f5_dir, '*.fast5'))
    if not f5_files:
        # Try zipped...
        logging.debug("No .fast5 files, maybe .fast5.gz?")
        f5_files = glob(os.path.join(f5_dir, '*.fast5.gz'))

    logging.debug("Found {} files".format(len('f5_files')))
    assert f5_files, "No fast5[.gz] files found."

    # Use the first one
    f5_file = f5_files[0]

    if f5_file.endswith('.gz'):
        # Unpack the entire file in memory - much faster than a direct read from gzip handle
        with BytesIO() as bfh:
            with gzip.open(f5_file, 'rb') as zfh:
                shutil.copyfileobj(zfh, bfh)
            bfh.seek(0)

            return read_fast5(bfh)
    else:
        # Let h5py open the file directly
        return read_fast5(f5_file)

def read_fast5(fobj):
    """Gets the metadata from a single fast5 file
       I'd assumed I could do this using ont_fast5_api but for various reasons it seems
       far simpler to code it myself. However I have looked at code from
       https://github.com/nanoporetech/ont_fast5_api/blob/master/ont_fast5_api/fast5_info.py
       as a starting point.
    """
    res = OrderedDict()
    for x in ['Fast5Version', 'StartTime', 'BaseCaller', 'BaseCallerTime', 'BaseCallerVersion']:
        res[x] = 'unknown'

    with h5py.File(fobj, 'r') as handle:

        # Version check. In development the files are '1.0'
        # so maybe I should check for this?
        res['Fast5Version'] = handle.attrs['file_version']

        # Just as the metadata is the same for each file, it's the same for each
        # read, so just get the first one.
        read0_name, read0 = next(iter((handle.items())))

        # Run ID (should be in the filename anyway!)
        res['RunID'] = read0.attrs['run_id']


        # Stuff from 'context_tags'
        for x in ['ExperimentType', 'SequencingKit', 'FlowcellType']:
            res[x] = 'unknown'
        try:
            res['ExperimentType'] = read0['context_tags'].attrs['experiment_type']
            res['SequencingKit'] = read0['context_tags'].attrs['sequencing_kit']
            res['FlowcellType'] = read0['context_tags'].attrs['flowcell_type']
        except KeyError:
            # Sometimes keys are missing, I guess.
            pass

        res['StartTime'] = read0['tracking_id'].attrs['exp_start_time']

        # Now look for basecalling metadata - there is some possible ambiguity
        # in the names here.
        bks = [k for k in read0['Analyses'] if k.startswith("Basecall_")]
        if len(bks) == 1:
            # OK we can get some info from it
            logging.debug("Basecall section is {}".format(bks[0]))
            bk = read0['Analyses'][bks[0]]
            res['BaseCaller'] = bk.attrs['name']
            res['BaseCallerTime'] = bk.attrs['time_stamp']
            res['BaseCallerVersion'] = bk.attrs['version']
        else:
            logging.debug("Found {} basecall sections".format(len(bks)))

    # Decode all byte strings in res.
    for k in list(res):
        try:
            res[k] = res[k].decode()
        except AttributeError:
            # Guess it's already decoded?
            pass

    return res

""" Here's what we expect to see in 'context_tags':
(Pdb) pp dict(read0['context_tags'].attrs)
{'basecall_config_filename': b'dna_r9.4.1_450bps_prom.cfg',
 'experiment_duration_set': b'3840',
 'experiment_type': b'genomic_dna',
 'fast5_output_fastq_in_hdf': b'1',
 'fast5_raw': b'1',
 'fast5_reads_per_folder': b'8000',
 'fastq_enabled': b'1',
 'fastq_reads_per_file': b'4000',
 'filename': b'pct0112_20190425_0004a30b00269581_2_a7_d7_sequencing_run_11608ge0009_79552',
 'flowcell_type': b'flo-pro002',
 'kit_classification': b'none',
 'local_basecalling': b'1',
 'sample_frequency': b'4000',
 'sequencing_kit': b'sqk-lsk109',
 'user_filename_input': b'11608ge0009'}
"""

""" Here's what we expect to see regarding the basecalling
(Pdb) pp dict(read0['Analyses']['Basecall_1D_000'].attrs)
{'name': b'MinKNOW-Live-Basecalling',
 'time_stamp': b'2019-04-25T16:25:18Z',
 'version': b'3.1.23'}
"""

def parse_args(*args):
    description = """Plots alignment scores in BAM over time"""

    parser = ArgumentParser( description = description,
                             formatter_class = ArgumentDefaultsHelpFormatter)

    parser.add_argument("fast5", default='.', nargs='?',
                        help="Directory to scan for .fast5[.gz] files")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Print progress to stderr")

    return parser.parse_args(*args)

if __name__=="__main__":
    main(parse_args())

