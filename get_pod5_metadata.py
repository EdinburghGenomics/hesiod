#!/usr/bin/env python3

"""Given a [directory of] .pod5 files, extract some metadata:
    1) Version of the .pod5 files
    2) Start time of the run
    3) Version of Guppy (or other basecaller)
    4) ...
   Inputs:
    A directory where .pod5 files may be found. It is assumed that any read
    from any file will yield the same metadata.
"""

import os, sys, re
import logging as L
import gzip
from tempfile import NamedTemporaryFile
import shutil
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from collections import OrderedDict
from contextlib import suppress
from pathlib import Path

# For parsing of ISO/RFC format dates (note that newer Python has datetime.datetime.fromisoformat
# but we're using dateutil.parser.isoparse from python-dateutil 2.8)
from dateutil.parser import isoparse

# For reading teh pod5...
import pod5

from hesiod import dump_yaml, glob

def main(args):

    L.basicConfig( level = L.DEBUG if args.verbose else L.INFO,
                         format = "{levelname}:{message}",
                         style = '{')

    if os.path.isdir(args.pod5):
        L.debug("Scanning .pod5[.gz] files in '{}'".format(args.pod5) )
        md = md_from_pod5_dir(args.pod5)
    else:
        L.debug("Reading from single file '{}'".format(args.pod5) )
        md = md_from_pod5_file(args.pod5)

    print(dump_yaml(md), end='')

def md_from_pod5_dir(p5_dir):
    """Read from the directory of pod5 files and return a dict of metadata.
    """
    p5_files = glob(os.path.join(p5_dir, '*.pod5'))
    if not p5_files:
        # Try zipped...
        L.debug("No .pod5 files, maybe .pod5.gz?")
        p5_files = glob(os.path.join(p5_dir, '*.pod5.gz'))

    L.debug("Found {} files".format(len(p5_files)))
    assert p5_files, "No pod5[.gz] files found."

    # Use the first one
    return md_from_pod5_file(p5_files[0])

def md_from_pod5_file(p5_file):
    """Read from a specified pod5 file and return a dict of metadata

        p5_file : filename to read
    """
    if p5_file.endswith('.gz'):
        # Unpack the entire file. For reasons noted in doc/pod5_format.txt this must be a named,
        # seek-able file.
        with NamedTemporaryFile(delete=True) as bfh:
            with gzip.open(p5_file, 'rb') as zfh:
                shutil.copyfileobj(zfh, bfh)
            bfh.flush()

            return read_pod5(bfh.name)
    else:
        # Let h5py open the file directly
        return read_pod5(p5_file)

def read_pod5(p5_filename):
    """Gets the metadata from the first read record in a single pod5 file
    """
    res = OrderedDict()
    for x in ['POD5Version', 'StartTime', 'Software']:
        res[x] = 'unknown'

    p5_handle = pod5.Reader(Path(p5_filename))
    try:
        # Version of the POD5 file. See
        # https://github.com/nanoporetech/pod5-file-format/issues/11
        res['POD5Version'] = p5_handle.file_version_pre_migration.public

        # Just as the metadata is the same for each file, it's the same for each
        # read, so just get the first one, and dict-ify it.
        # Note - I could get at the same info in a less convenient format with:
        #   p5_handle.run_info_table.get_batch(0)
        read0 = vars(next(p5_handle.reads()).run_info)

        # Run ID used to be in the filename, but to be sure get it here
        res['RunID'] = read0['acquisition_id']
        res['Software'] = read0['software']

        # Redundant but still useful to extract
        res['FlowcellId'] = read0['flow_cell_id']
        res['FlowcellType'] = read0['flow_cell_product_code']
        res['Sample'] = read0['sample_id']

        # Stuff from 'context_tags'
        context_tags = dict(read0['context_tags'])
        res['ExperimentType'] = context_tags.get('experiment_type', 'unknown')
        res['SequencingKit']  = context_tags.get('sequencing_kit', 'unknown')
        res['BasecallConfig'] = context_tags.get('basecall_config_filename', 'unknown')

        res['SamplingFrequency'] = read0.get('sample_rate', 'unknown')
        try:
            res['SamplingFrequency'] = f"{res['SamplingFrequency']/1000} kHz"
        except TypeError:
            # Leave it as-is
            pass

        # Stuff from 'tracking_id'
        tracking_id = dict(read0['tracking_id'])

        # This is useful, being the experiment start time not the read start time
        res['StartTime']    = tracking_id['exp_start_time']
        # Note that 'guppy_version' will contain the Dorado version if Dorado is used
        # We'll rely on read0['software'] from now on.
        #res['GuppyVersion'] = tracking_id['guppy_version']

    finally:
        p5_handle.close()

    # Decode all byte strings in res, and re-format dates.
    for k in list(res):
        with suppress(AttributeError):
            res[k] = res[k].decode()

        if k.endswith("Time"):
            res[k] = isoparse(res[k]).strftime('%A, %d %b %Y %H:%M:%S')

    return res


def parse_args(*args):
    description = """Extract various bits of metadata from the first read in a .pod5 file."""

    parser = ArgumentParser( description = description,
                             formatter_class = ArgumentDefaultsHelpFormatter)

    parser.add_argument("pod5", default='.', nargs='?',
                        help="File to read, or directory to scan for .pod5[.gz] files")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Print progress to stderr")

    return parser.parse_args(*args)

if __name__=="__main__":
    main(parse_args())

