#!/usr/bin/env python3
import os, sys, re
import logging as L
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from pprint import pformat

from hesiod import parse_cell_name, glob

""" Makes a summary (in text format) for a run, mostly for the benefit of RT.

    This wants to be able to run before any processing happens, unlike the reports.
    Unlike make_report, this does not want to be supplied with a list of .yaml files,
    but rather it will scan for available data.
"""

def main(args):

    L.basicConfig(level=(L.DEBUG if args.debug else L.WARNING))
    def pf(filename):
        return os.path.join(args.dir, 'pipeline', filename)

    # Start by reporting the working dir
    rep = [os.path.realpath(args.dir)]

    if args.runid:
        runid = args.runid
    else:
        runid = os.path.basename(os.path.realpath(args.dir))

    if args.cells:
        cells = args.cells.split('\t')
    else:
        cells = scan_cells(args.dir)

    if args.upstream:
        upstream = args.upstream
    else:
        # In that case, this file must exist...
        with open(pf('upstream')) as ufh:
            upstream = ufh.read().strip()
    if upstream == 'LOCAL':
        upstream = None

    # Report is fairly simple right now.
    rep.append( "Run {}{} with {} cells".format(runid,
                                                " ({})".format(upstream) if upstream else "",
                                                len(cells)) )
    rep.append("")

    # Now for each cell. Report them in slot order (how does one correctly sort that?)
    cell_infos = sorted([ (c, parse_cell_name(c)) for c in cells ], key=lambda i: i[1].get('Slot', ''))

    # Could also get this from the caller??
    for cellname, ci in cell_infos:
        basename = cellname.split('/')[-1]
        if os.path.exists( pf('{}.done'.format(basename)) ):
            ci['Status'] = "done"
        elif os.path.exists( pf('{}.started'.format(basename)) ):
            ci['Status'] = "in qc"
        elif os.path.exists( pf('{}.synced'.format(basename)) ):
            ci['Status'] = "need qc"
        else:
            ci['Status'] = "sync"

    '''
    for cellname, ci in cell_infos:
        rep.append("Slot ~{}~:".format(ci.get('Slot', '???')))
        # "Library Date Number Slot CellID Checksum"
        for k, v in ci.items():
            if k != 'Slot':
                rep.append("  {:8s}: {}".format(k, v))
        rep.append("")
    '''

    # Or should that be a table?
    rep.append(" Slot      | CellID    | Status  | Cell")
    rep.append("-----------|-----------|---------|-" + "-" * max(len(c) for c in cells))
    for cellname, ci in cell_infos:
        rep.append(" {:10s}| {:10s}| {:8s}| {:s}".format( ci.get('Slot', '???'),
                                                          ci.get('CellID'),
                                                          ci['Status'],
                                                          cellname))
    rep.append("")

    if (not args.txt) or (args.txt == '-'):
        print(*rep, sep="\n")
    else:
        L.info("Writing to {}.".format(args.out))
        with open(args.txt, "w") as ofh:
            print(*rep, sep="\n", file=ofh)

def scan_cells(run_dir):
    """Same logic as found in Snakefile.main. This only works after things are synced.
    """
    return [ '/'.join(fs.strip('/').split('/')[-3:-1])
             for fs in glob( "{}/*/*/fastq_pass/".format(run_dir) ) ]

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
    argparser.add_argument("--upstream",
                            help="Hint the upstream location for this run.")
    argparser.add_argument("--cells",
                            help="Hint what we expect the cells to be.")
    argparser.add_argument("-d", "--debug", action="store_true",
                            help="Print more verbose debugging messages.")

    return argparser.parse_args(*args)

if __name__ == "__main__":
    main(parse_args())
