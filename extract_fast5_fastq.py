#!/usr/bin/env python3

import os, sys, re
import logging
from io import BytesIO
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter

import h5py

def main(args):

    logging.basicConfig( level = logging.DEBUG if args.verbose else logging.INFO,
                         format = "{levelname}:{message}",
                         style = '{')

    for f5_file in args.fast5:
        # Open file, which may be gzipped
        if f5_file.endswith('.gz'):
            # Unpack the entire file in memory - much faster than a direct read from gzip handle
            with BytesIO() as bfh:
                with gzip.open(f5_file, 'rb') as zfh:
                    shutil.copyfileobj(zfh, bfh)
                bfh.seek(0)

                fastq_data = read_fast5(bfh)
        else:
            # Let h5py open the file directly
            fastq_data = read_fast5(f5_file)

    print(fastq_data)

def read_fast5(fobj):
    """Read the file object, or if fobj is a string it will be interpreted as
       a file name to open.
    """
    with h5py.File(fobj, 'r') as handle:

        import pdb ; pdb.set_trace()

        print("ooo")


def parse_args(*args):
    description = """Dump FASTQ (2D basecalled sequence) from a FAST5 file."""

    parser = ArgumentParser( description = description,
                             formatter_class = ArgumentDefaultsHelpFormatter)

    parser.add_argument("fast5", default='.', nargs='+',
                        help="One or more .fast5[.gz] files")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Print debugging info to stderr")

    return parser.parse_args(*args)

if __name__=="__main__":
    main(parse_args())

