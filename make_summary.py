#!/usr/bin/env python3
import os, sys, re
import logging as L
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from pprint import pformat
def glob():
    """Regular glob() is useful but it can be improved like so.
    """
    from glob import glob
    return lambda p: sorted( (f.rstrip('/') for f in glob(os.path.expanduser(p))) )
glob = glob()

""" Makes a summary (in text format) for a run, mostly for the benefit of RT.

    This wants to be able to run before any processing happens, unlike the reports.
    Unlike make_report, this does not want to be supplied with a list of .yaml files,
    but rather it will scan for available data.
"""

def main(args):

    L.basicConfig(level=(L.DEBUG if args.debug else L.WARNING))

    rep = ["Placeholder for real report"]

    if (not args.txt) or (args.txt == '-'):
        print(*rep, sep="\n")
    else:
        L.info("Writing to {}.".format(args.out))
        with open(args.txt, "w") as ofh:
            print(*rep, sep="\n", file=ofh)

def parse_args(*args):
    description = """ Makes a summary (in text format) for a run, by scanning the directory.
                      Unlike make_report.py, this one always runs on the original source dir,
                      not the output directory, and does not save/use any intermadiate YAML
                      files.
                  """
    argparser = ArgumentParser( description=description,
                                formatter_class = ArgumentDefaultsHelpFormatter )
    argparser.add_argument("--txt",
                            help="Where to save the textual report. Defaults to stdout.")
    argparser.add_argument("--dir", default=".",
                            help="Where to scan, if not the current dir.")
    argparser.add_argument("--runid",
                            help="Hint what we expect the run ID to be.")
    argparser.add_argument("-d", "--debug", action="store_true",
                            help="Print more verbose debugging messages.")

    return argparser.parse_args(*args)

if __name__ == "__main__":
    main(parse_args())
