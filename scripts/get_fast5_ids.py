#!/usr/bin/env python3

"""Given a FAST5 file (or files), extract the IDs of all the individual
   reads in the file.
"""

import os, sys, re
import logging
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from contextlib import suppress

# For reading teh fast5 (use the virtualenv to get this!)
import h5py

def main(args):

    logging.basicConfig( level = logging.DEBUG if args.verbose else logging.INFO,
                         format = "{levelname}:{message}",
                         style = '{')

    for f in args.fast5:
        logging.debug("Reading from single file '{}'".format(f) )
        id_list = ids_from_fast5_file(f)

        print(*id_list, sep="\n")

def ids_from_fast5_file(f5_file):
    """Gets the the IDs from a single fast5 file
       I'd assumed I could do this using ont_fast5_api but for various reasons it seems
       far simpler to code it myself. However I have looked at code from
       https://github.com/nanoporetech/ont_fast5_api/blob/master/ont_fast5_api/fast5_info.py
       as a starting point.
    """
    res = []
    with h5py.File(f5_file, 'r') as handle:

        for areadname, aread in handle.items():

            res.append(areadname)
    return res

def parse_args(*args):
    description = """Extract all read IDs from a FAST5 file."""

    parser = ArgumentParser( description = description,
                             formatter_class = ArgumentDefaultsHelpFormatter )

    parser.add_argument("fast5", nargs='+',
                        help="Fast5 file(s) to scan")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Print progress to stderr")

    return parser.parse_args(*args)

if __name__=="__main__":
    main(parse_args())

