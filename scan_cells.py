#!/usr/bin/env python3

"""This script generates sc_data.yaml.

   It does not modify anything - you can run it in any prom_runs
   directory like:

   $ scan_cells.py --cells 27051AT0005/20230608_0921_1C_PAQ21042_2a207d10 .
"""

from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
import logging as L
from itertools import product
from functools import partial
from pprint import pprint, pformat

from hesiod import ( glob, groupby, parse_cell_name, load_final_summary,
                     fast5_out, find_summary, dump_yaml )

DEFAULT_FILETYPES_TO_SCAN = ["fastq", "fastq.gz", "fast5", "pod5", "bam"]

def main(args):

    L.basicConfig( level = L.DEBUG if args.verbose else L.INFO,
                         format = "{levelname}:{message}",
                         style = '{' )

    if not args.missing_ok and not glob(f"{args.expdir}/."):
        exit(f"No such directory {args.expdir}. Use -m to look for output files in CWD.")

    # Call scan_main, which is amenable to testing
    res = scan_main(args)

    print( dump_yaml(res), end='' )

def scan_main(args):
    # This will yield a dict with scanned_cells and counts as keys
    res = scan_cells(args.expdir, cells = args.cells,
                                  cellsready = args.cellsready,
                                  look_in_output = args.missing_ok,
                                  subset = args.subset)
    sc = res['scanned_cells']

    # Find a representative FAST5 and POD5 per cell
    for c, v in sc.items():
        rep_fast5 = res.setdefault('representative_fast5', dict())
        rep_fast5[c] = find_representative_fast5( cell = c,
                                                  infiles = v,
                                                  try_glob = args.missing_ok )
        rep_pod5 = res.setdefault('representative_pod5', dict())
        rep_fast5[c] = find_representative_pod5( cell = c,
                                                 infiles = v,
                                                 batch_size = args.pod5_batch_size,
                                                 try_glob = args.missing_ok )

    # Note the pod5_batch_size setting
    res['pod5_batch_size'] = args.pod5_batch_size

    # Add printable counts
    res['printable_counts'] = sc_counts(sc)

    # And cells by project and by library, in order
    sc_sorted = sorted(sc)
    res['cells_per_project'] = groupby( sc_sorted,
                                        keyfunc = lambda c: parse_cell_name('-', c)['Project'],
                                        sort_by_key = True )
    res['cells_per_pool']     = groupby( sc_sorted,
                                         keyfunc = lambda c: parse_cell_name('-', c)['Pool'],
                                         sort_by_key = True)

    return res

def scan_cells( expdir, cells=None, cellsready=None,
                        look_in_output = False,
                        subset = None,
                        filetypes_to_scan = DEFAULT_FILETYPES_TO_SCAN ):
    """ Work out all the cells to process. Normally simple since the list is just passed in
        by driver.sh directly but I do want to be able to process all the cells by default so
        there is some scanning capability too.
        Then get a categorised index of all the files per cell.

        res['scanned_cells'] structure is { cell : barcode : 'fastX_pass' : [ list of files ] }
        res['counts'] is headline counts for cells found
    """
    # Implement subset by providing a glob function with a baked-in limit
    globn = partial(glob, limit=subset)

    if cells is None:
        if expdir:
            # Look for valid cells in the input files
            cells = sorted(set( '/'.join(fs.strip('/').split('/')[-3:-1])
                                for fs in glob(f"{expdir}/*/*/fastq_????/") ))
        else:
            # No cells in input, but maybe we can look at the output
            L.debug("No cells in expdir")
            cells = []
        if not cells and look_in_output:
            L.debug("Looking for output files instead")
            # Look for cells here in the output (presumably the experiment already processed and
            # the rundata was removed)
            cells = [ '/'.join(fs.strip('/').split('/')[-3:-1]) for fs in glob("*/*/cell_info.yaml") ]

    if cellsready is None:
        # This should include the cells to be processed now AND those already processed.
        if expdir:
            # Look for cells with a final_summary.txt (as made by MinKNOW).
            cellsready = [ c for c in cells if
                           find_summary( rundir = expdir,
                                         cell = c ,
                                         pattern = "final_summary.txt",
                                         allow_missing = True ) ]
        else:
            # If there is no EXPDIR this makes most sense by default.
            cellsready = cells

    for c in cellsready:
        assert c in cells, f'Invalid cell (no fastq_pass or not listed in config["cells"]): {c}'

    if not cellsready:
        # Not a fatal error but warrants a warning
        L.warning("List of cells to process is empty")

    res = { c: dict() for c in cellsready }

    # A place to store the skip files we otherwise ignore
    skipped_skip_files = {}

    if expdir:
        for c, d in res.items():
            for pf, filetype in product(["pass", "fail"], filetypes_to_scan):
                category = f"{filetype}_{pf}"
                cat_dir  = f"{filetype.split('.')[0]}_{pf}"
                # Collect un-barcoded files
                non_barcoded_files = [ f[len(expdir) + 1:]
                                       for f in globn(f"{expdir}/{c}/{cat_dir}/*.{filetype}") ]
                barcoded_files = [ f[len(expdir) + 1:]
                                   for f in globn(f"{expdir}/{c}/{cat_dir}/*/*.{filetype}") ]
                if non_barcoded_files:
                    d.setdefault('.', dict())[category] = non_barcoded_files
                for bf in barcoded_files:
                    # Keys in d are to be the barcodes which we extract from the filenames like so:
                    _, barcode, _ = bf[len(c) + 1:].split('/')
                    d.setdefault(barcode, dict()).setdefault(category, list()).append(bf)

        # Some fixing-upping...
        for c, d in res.items():
            # We may have files in fast5_skip (or pod5_skip) but these are never barcoded, nor are
            # there any fastq files, since they are not even basecalled. They do need to be
            # included in the tally when checking vs. the final summary.
            # For non-barcoded runs I'll tack them on with fast5_fail. For barcoded runs they go in
            # unclassified/fast5_fail. This seems to be fairly reasonable.
            # Oh and we apparently need to do this for BAM files too? Let's just do it for all
            # types.
            for filetype in filetypes_to_scan:
                files_in_skip = [ f[len(expdir) + 1:]
                                  for f in globn(f"{expdir}/{c}/{filetype}_skip/*") ]

                # For Promethion, at present, the skip files actually go into fast5_fail/.
                # not fast5_skip/ but by my logic when there are barcodes these need to be in
                # 'unclassified' so detect this case first and pull them out before making the
                # empty lists.
                if 'unclassified' in d and d.get('.',{}).get(f"{filetype}_fail"):
                    files_in_skip.extend(d['.'][f"{filetype}_fail"])
                    del d['.'][f"{filetype}_fail"]
                    if not d['.']:
                        # This is like rmdir - only remove the key if it now points to an empty dict.
                        del d['.']

                # Whatever we got in the skip, work out where to put it
                if 'unclassified' in d:
                    d['unclassified'].setdefault(f"{filetype}_fail",[]).extend( files_in_skip )
                elif '.' in d:
                    d['.'].setdefault(f"{filetype}_fail",[]).extend( files_in_skip )
                else:
                    # Should never happen?
                    skipped_skip_files[(c,filetype)] = files_in_skip

            # Add in empty lists for missing items.
            # A quirk of the logic above is that barcodes with "fail" reads but no "pass" reads
            # are listed after those with "pass" reads, and this carries into the reports. If this
            # is a problem, this is the place to fix it by sorting all dicts within res.
            for bcdict in d.values():
                for pf, filetype in product(["pass", "fail"], filetypes_to_scan):
                    # If the barcode is there we should have all four categories in bcdict
                    bcdict.setdefault(f"{filetype}_{pf}", [])

        # Sanity-check that the file counts match with final_summary.txt
        for c, d in res.items():
            fs = load_final_summary(f"{expdir}/{c}/")
            for ft in ["fastq", "fast5", "pod5"]:
                # Add zipped and unzipped FASTQ files...
                ft_sum = sum( len(fileslist[f"{ft}{z}_{pf}"])
                                for fileslist in d.values()
                                for z in (["", ".gz"] if ft == "fastq" else [""])
                                for pf in ["pass", "fail"] )
                # Account for skipped_skip_files
                if skipped_skip_files.get((c,ft)):
                    L.warning(f"skipped_skip_files is non-empty for {(c,ft)}:"
                              F" {skipped_skip_files[(c,ft)]}")
                    ft_sum += len( skipped_skip_files[(c,ft)] )

                ft_expected = fs.get(f'{ft}_files_in_final_dest', 0)
                if ft_sum != ft_expected and (subset is None):
                    raise RuntimeError( f"Mismatch between count of {ft.upper()} files for {c}:\n" +
                                        f"{ft_sum} (seen) != {ft_expected} (in final_summary.txt)" )

    # Return the dict of stuff to process, and other counts we've calculated
    counts = dict( cells = len(cells),
                   cellsready = len(cellsready),
                   cellsaborted = 0 )
    return dict( scanned_cells = res,
                 counts = counts )

def sc_counts(sc_dict, width=140, show_zeros=True):
    """ Make a printable summary of SC
    """
    # Make a dict that just shows the counts
    sc_counts = { c : { bc: { category: f"<{len(filelist)} files>"
                              for category, filelist in d.items()
                              if (show_zeros or filelist) }
                        for bc, d in bc_dict.items() }
                  for c, bc_dict in sc_dict.items() }

    # Ideally I'd use sort_dicts=False but that needs Py3.8
    return pformat(sc_counts, width=width)

def find_representative_fast5(cell, infiles, try_glob=False):
    """Find a suitable fast5 file to scan for metadata. The assumption is that all contain
       the same metadata.  This returns the .fast5 file as it will be created
       in the output directory by using the list of files globbed from the input directory.
       If try_glob is True, the fallback if sc has no candidates will be to scan the
       output directory itself.
    """
    fast5_pass = [ plist for bc in infiles.values() for plist in bc['fast5_pass']  ]
    fast5_fail = [ flist for bc in infiles.values() for flist in bc['fast5_fail']  ]
    if fast5_pass:
        # Depend on the first file provided by SC[wc.cell] for any barcode
        return fast5_out(fast5_pass[0])
    elif fast5_fail:
        # Sometimes everything fails
        return fast5_out(fast5_fail[0])
    elif try_glob:
        # Look for an existing output file.
        globbed = glob(f"{cell}/fast5_*_????/*.fast5")
        if globbed:
            return globbed[0]
        else:
            return None
    else:
        return None

def find_representative_pod5(cell, infiles, batch_size, try_glob=False):
    """Find a suitable fast5 file to scan for metadata. The assumption is that all contain
       the same metadata.
    """
    # As we now batch up the pod5 files, the names are more predicatable than when we had
    # fast5 files, and the name of the first one will be:
    #
    # {cell}/pod5_{bc}_{pf}/batch{POD5_BATCH_SIZE}_{b:08d}.pod
    pod5_pass = [ bc for bc, bcparts in infiles.items() for plist in bcparts['pod5_pass']  ]
    pod5_fail = [ bc for bc, bcparts in infiles.items() for flist in bcparts['pod5_fail']  ]

    if pod5_pass:
        bc = pod5_pass[0]
        pf = "pass"
    elif pod5_fail:
        bc = pod5_fail[0] # We have no passing reads, but we have fails and can still report
        pf = "fail"
    elif try_glob:
        # In this case, just look for any output file
        globbed = glob(f"{cell}/pod5_*_????/*.pod5")
        return globbed[0] if globbed else None
    else:
        # We really have nothing
        return None

    batch = 0  # This will always be padded to 8 digits
    return f"{cell}/pod5_{bc}_{pf}/batch{batch_size}_{batch:08d}.pod"

def parse_args(*args):
    description = """Scan the input files for all cells, to provide a work plan for Snakemake"""

    parser = ArgumentParser( description = description,
                             formatter_class = ArgumentDefaultsHelpFormatter)

    parser.add_argument("expdir", default='./rundata', nargs='?',
                        help="Directory to scan for cells and fastq/fast5 files")

    parser.add_argument("-c", "--cells", nargs='+',
                        help="Cells in this Experiment. If not specified, they will be scanned.")
    parser.add_argument("-r", "--cellsready", nargs='+',
                        help="Cells to process now. If not specified, the script will check all the cells.")
    parser.add_argument("--pod5_batch_size", type=int, default=100,
                        help="Number of POD5 files to merge into a single file.")

    # The point of this is that if the pipeline is being re-run, ./rundata may have been deleted but we can
    # still look at the outut files to reconstruct the info. But unless the pipeline has previously run and
    # copied all the data then trying to look in the current dir will see nothing, or incomplete data.
    parser.add_argument("-m", "--missing_ok", action="store_true",
                        help="If expdir is missing or incomplete, scan files in current dir.")

    parser.add_argument("--subset", type=int,
                        help="Only report the first N files per barcode. Useful for debugging only.")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Print more logging to stderr")

    return parser.parse_args(*args)

if __name__=="__main__":
    main(parse_args())

