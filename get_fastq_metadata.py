#!/usr/bin/env python3

"""Given a (directory of) .fastq(.gz) file(s), extract some metadata from the first line:
    1) runid
    2) Start time of the run
    3) flow_cell_id
    4) barcode
    5) basecall_model (apparently we can't get this from elsewhere)
   Inputs:
    A directory where .fastq(.gz) files may be found, or a file
"""

import os, sys, re
import logging
import gzip
import shutil
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from collections import OrderedDict
from contextlib import suppress

# For parsing of ISO/RFC format dates (note that newer Python has datetime.datetime.fromisoformat
# but we're using dateutil.parser.isoparse from python-dateutil 2.8)
# Actually, the time in the header lines here is per-read, and not useful to us anyway.
# The POD5 file knows the cell start time.
#from dateutil.parser import isoparse

from hesiod import dump_yaml, glob

def main(args):

    logging.basicConfig( level = logging.DEBUG if args.verbose else logging.INFO,
                         format = "{levelname}:{message}",
                         style = '{')

    if os.path.isdir(args.fastq):
        logging.debug(f"Scanning .fastq[.gz] files in {args.fastq!r}")
        md = md_from_fastq_dir(args.fastq)
    else:
        logging.debug(f"Reading from single file {args.fastq!r}")
        md = md_from_fastq_file(args.fastq)

    print(dump_yaml(md), end='')

def md_from_fastq_dir(fq_dir):
    """Read from the directory of fastq files and return a dict of metadata
       from the first header of the first file.
    """
    fq_files = glob(os.path.join(fq_dir, '*.fastq.gz'))
    if not fq_files:
        # Try unzipped...
        logging.debug("No .fastq.gz files, maybe .fastq?")
        fq_files = glob(os.path.join(fq_dir, "*.fastq"))

    logging.debug(f"Found {len(fq_files)} files")
    if not fq_files:
        raise RuntimeError("No fastq[.gz] files found.")

    # Use the first one
    return md_from_fastq_file(fq_files[0])

def md_from_fastq_file(fq_file):
    """Read from a specified fastq file and return a dict of metadata
    """
    _open = gzip.open if fq_file.endswith('.gz') else open
    with _open(fq_file, 'rt') as fh:
        first_line = next(fh)

        if not first_line.startswith("@"):
            raise RuntimeError(f"Not a FASTQ header line:\n{first_line}")

    return md_from_header_line(first_line.rstrip("\n"))

def md_from_header_line(hline):
    """Extract the goodies from the header line.
    """
    hdict = dict([p.split("=", 1) for p in hline.split() if "=" in p])

    res = OrderedDict()

    for k, v in dict( runid = None,
                      flowcell = "flow_cell_id",
                      experiment = "protocol_group_id",
                      sample = "sample_id",
                      barcode = None,
                      basecall_model = "basecall_model_version_id" ).items():
        if hdict.get(v or k):
            res[k] = hdict.get(v or k)

    # Add this if missing
    for x in ['basecall_model']:
        res.setdefault(x, 'unknown')

    return res

def parse_args(*args):
    description = """Extract various bits of metadata from the first read in a FASTQ file."""

    parser = ArgumentParser( description = description,
                             formatter_class = ArgumentDefaultsHelpFormatter)

    parser.add_argument("fastq", default='.', nargs='?',
                        help="A file, or a directory to scan for .fastq[.gz] files")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Print progress to stderr")

    return parser.parse_args(*args)

if __name__=="__main__":
    main(parse_args())

