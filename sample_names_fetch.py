#!/usr/bin/env python3

import os, sys, re
import ast
import logging as L
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
import csv
import shutil
from collections import Counter

from hesiod import parse_cell_name, glob, dump_yaml

def main(args):

    L.basicConfig(level=(L.DEBUG if args.debug else L.WARNING))

    # Turns r'\t' into '\t' the fancy way
    delim = ast.literal_eval(f"'{args.delim}'")

    experiment = args.experiment or os.path.dirname(os.path.abspath('.'))
    cell, = args.cell

    if args.find:
        # In this case, just find the file and quit
        tsv_file = find_tsv(experiment, cell, args.tsvdir)
        if tsv_file:
            print(tsv_file)
            exit(0)
        else:
            exit(1)

    # Get the YAML which might be a sample list or might be an error.
    info_dict = get_info_main(experiment, cell, args.tsvdir, delim)

    if args.print:
        # Print and done
        print(dump_yaml(info_dict), end='')
    else:
        # Copy the TSV file to the cell dir, and save the YAML.
        # At this point, the cell dir must exist
        if 'error' not in info_dict:
            orig_filename = os.path.basename(info_dict['file'])
            shutil.copyfile(info_dict['file'], f"{cell}/{orig_filename}")

        dump_yaml(info_dict, filename=f"{cell}/sample_names.yaml")

def get_info_main(experiment, cell, dir, delim):

    error = None

    # See if we can find a sample names file for this cell
    if not os.path.isdir(dir):
        error = f"No such directory {dir}"
    else:
        tsv_file = find_tsv(experiment, cell, dir)
        if not tsv_file:
            error = f"No suitable TSV file found in {dir}"

    if error:
        return dict( error = error,
                     file = None )

    # Well, we have a file
    res = parse_tsv(tsv_file, delim=delim)

    # Add the file and return
    res['file'] = os.path.abspath(tsv_file)
    return res

def find_tsv(experiment, cell, dir='.'):
    """Locate a sample names TSV file to use for this cell.
    """
    parsed_cell = parse_cell_name(experiment, cell)

    # For a pooled flowcell the 'Library' will be a pool name.
    # CellID is the flowcell ID and project is like 12345
    candidate_tsv = [ f"{parsed_cell[x]}_sample_names.tsv" for x in
                      [ 'Library', 'CellID', 'Project' ] ]

    # The rule is that we search dir/*.tsv and dir/*/*.tsv. Precedence is in the
    # order of candidate_tsv. If there are multiple files the one in the top level takes
    # precedence, then in alphabetical order. So...
    all_tsv = glob(f"{dir}/*.tsv") + glob(f"{dir}/*/*.tsv")

    for cand in candidate_tsv:
        for f in all_tsv:
            if os.path.basename(f) == cand:
                return f

    return None


def parse_tsv(filename, delim="\t"):

    error = None
    codes = []

    try:
        with open(filename, newline='') as csvfile:
            tsvreader = csv.reader(csvfile, delimiter=delim)
            for n, row in enumerate(tsvreader):

                # Blank rows are ignored.
                if not row:
                    continue
                if not re.fullmatch(r'barcode\d\d', row[0]):
                    if n == 0:
                        # Header row does not need to be a barcode
                        continue
                    else:
                        # Other rows do need to be a barcode
                        error = f"Unable to parse line {n+1}"
                        break
                if len(row) == 1:
                    error = f"Missing internal name for {row[0]}"
                    break
                if not re.fullmatch(r'\d{5}[A-Z]{2}\w*', row[1]):
                    error = f"Invalid internal name for {row[0]}"
                    break

                codes.append( dict( bc = row[0],
                                    int_name = row[1],
                                    ext_name = ' '.join(row[2:]).strip() or row[1] ) )
    except OSError as e:
        # Catches exceptions where the file cannot be read
        error = str(e)

    # OK we gottem. Now some sanity checks
    if not error:
        if not codes:
            error = "No barcodes found in the file"
        else:
            rep_bc, = Counter([ c['bc'] for c in codes ]).most_common(1)
            rep_id, = Counter([ c['int_name'] for c in codes ]).most_common(1)

            if rep_bc[1] > 1:
                error = f"Repeated barcode {rep_bc[0]}"
            elif rep_id[1] > 1:
                error = f"Repeated internal name {rep_id[0]}"

    if not error:
        # Yay all tests passed
        return dict( barcodes = codes )
    else:
        return dict( error = error )


def parse_args(*args):
    description = """Finds an appropriate sample_names.tsv for a given cell.
                     Copies the file to the cell directory, and also makes
                     a sample_names.yaml with the information in YAML format,
                     or an error if finding or parsing the file fails.
                  """
    argparser = ArgumentParser( description=description,
                                formatter_class = ArgumentDefaultsHelpFormatter )
    argparser.add_argument("cell", nargs=1,
                            help="The cell to find samples for.")
    argparser.add_argument("--experiment",
                           help="Name of experiment. Defaults to basename of CWD.")
    argparser.add_argument("-t", "--tsvdir", default=os.environ.get("SAMPLE_NAMES_DIR", '.'),
                           help="Directory to search for candidate TSV files.")
    argparser.add_argument("--delim", default="\\t",
                           help="Directory to search for candidate TSV files.")
    argparser.add_argument("--find", action="store_true",
                            help="Find and print the TVS filename then quit.")
    argparser.add_argument("--print", action="store_true",
                            help="Print the YAML but do not save any files.")
    argparser.add_argument("-d", "--debug", action="store_true",
                            help="Print more verbose debugging messages.")

    return argparser.parse_args(*args)

if __name__ == "__main__":
    main(parse_args())
