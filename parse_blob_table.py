#!/usr/bin/env python3

""" Reimplementation of Jon's parseBlobTable.R in Python, because I can't be having with R.
    Results should be byte-identical with Jon's old code.
    See http://gitlab.genepool.private/production-team/qc_tools_python/blob/master/scripts/parseBlobTable.R
"""

import os, sys, re
import logging as L
from copy import deepcopy
from collections import Counter
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter

def read_blob_table(fh):
    """Read the lines from the .blobplot.stats.txt, which is mostly a tab-separated file.
       Return (colnames, name_map, datalines)
    """
    headerlines = []
    colnames = []
    datalines = []

    for l in fh:
        l = l.strip()

        # Special case - if the first line simpy says 'No data' then there was no data.
        if l == 'No data' and not headerlines:
            return ([], {}, [])

        if not l:
            # Not expecting blank lines, but skip them if seen.
            continue
        if l.startswith('## '):
            headerlines.append(l[3:])
        elif l.startswith('# '):
            assert not colnames # Should only see one such line
            colnames = l[2:].split("\t")
        else:
            datalines.append(l.split("\t"))
            assert len(datalines[-1]) == len(colnames)

    # Now extract a name mapping dict from the headerlines
    name_map = { l.split('=')[0] : re.sub('(\+.*|\.[^.]*)$', '', l.split('/')[-1])
                 for l in headerlines
                 if re.match(r'(bam|cov)[0-9]+=', l) }

    # There should be no tab chars in any names
    assert not any(re.search(r'\t', n) for n in name_map.keys())
    assert not any(re.search(r'\t', n) for n in name_map.values())

    # Coerce every value in a _read_map column to an integer, and each _read_map_p
    # column to a float
    for dl in datalines:
        for i, colname in enumerate(colnames):
            if colname.endswith('_read_map'):
                dl[i] = int(dl[i].replace(',',''))
            elif colname.endswith('_read_map_p'):
                dl[i] = float(dl[i].replace('%',''))

    # That's what we need!
    return (colnames, name_map, datalines)

def main(args):

    L.basicConfig(level=(L.DEBUG if args.debug else L.WARNING))

    # Do all the parsing first. The tables won't be large so having everything in
    # memory at once is fine.
    all_tables = []
    for f in args.statstxt:
        with open(f) as fh:
            all_tables.append(read_blob_table(fh))

    # Now I can have a master Matrix
    mm = Matrix('taxon', 'lib', numsort=('taxon'))
    total_reads_per_lib = Counter()

    for colnames, name_map, datalines in all_tables:

        # Empty file?
        if not datalines: continue

        # Since I'm not using a table datatype, make my own index of the column names
        colidx = { n: i for i, n in enumerate(colnames) }

        # (Comment from Jon)
        # Get the actual read numbers so we can calculate a more precise percentage
        # than Blobtools provides. Then we can see how close to 0 some of these 0
        # percentages are.
        #
        # Blobtools' percentage values are relative to the origninal read counts
        # (mapped and unmapped). If we want to re-calculate the percentages we need to
        # re-infer that original read cout. We can use the 'all' percent to do that.
        # It won't be completely right due to rounding error in the 'all' percentage
        # itself. But it should be close enough. Of course we might find it more
        # useful in future to have percentages relative to the mapped reads.

        # Having moved the data coercion into the read_blob_table() function, I can now
        # just do that calculation. First estimate the total reads per lib based off the
        # 'all' row.
        all_row, = [ dl for dl in datalines if dl[colidx['name']] == 'all' ]
        total_reads_per_bam = Counter()
        for n in name_map:
            total_reads_per_bam[n] = (all_row[colidx[n+'_read_map']] * 100) / all_row[colidx[n+'_read_map_p']]

            # We also keep a master count
            total_reads_per_lib[name_map[n]] += total_reads_per_bam[n]

        # We've now also verified that all names in the name map have corresponding columns,
        # but are all columns present in the name_map?
        for colname in colnames:
            if colname.endswith('_read_map_p') and colname != 'covsum_read_map_p':
                assert name_map[colname[:-len('_read_map_p')]]

        # Strip out rows that have name in ['all', 'no-hit', 'undef', 'other']
        # FIXME - maybe I want 'other' left in?
        datalines = [ dl for dl in datalines
                      if dl[colidx['name']] not in ['all', 'no-hit', 'undef'] ]

        # Now recalculate all the percentages relative to this value, and pop them into
        # my master matrix.
        for dl in datalines:
            for n in name_map:
                total_reads = total_reads_per_bam[n]
                mapped_reads = dl[colidx[n+'_read_map']]
                new_pct = (mapped_reads * 100) / total_reads
                # The new value should be close to the old one.
                assert abs(dl[colidx[n+'_read_map_p']] - new_pct) < 0.1

                # Into the matrix with ye!
                # The mm.add() method will object if a value was already present.
                mm.add(new_pct, taxon=dl[colidx['name']], lib=name_map[n])

    # End of loop through all_tables

    # Now prune out taxa with nothing that makes the cutoff - but first see what is
    # the highest number. Due to our sorting strategy this will always be in the leftmost
    # taxon column.
    max_percent = "None"
    for tax in mm.list_labels('taxon')[:1]:
        max_percent = "{:.{}f}".format(max( mm.get_vector('taxon', tax) ), args.round)

    mm.prune('taxon', lambda v: v >= args.cutoff)

    # And print the result. As it's TSV and we've already checked for tabs this is safe.
    if args.output == '-':
        fh = sys.stdout
    else:
        fh = open(args.output, 'x')

    if not mm.list_labels('taxon'):

        # Jon had this so I'll (kinda) copy it...
        # taxlevel <- unlist(strsplit(basename(files[1]), '\\.'))[2]
        try:
            taxlevel = args.statstxt[0].split('/')[-1].split('.')[-4]
        except IndexError:
            taxlevel = "taxon"

        print('No {taxlevel} is represented by at least {limit}% of reads (max {max}%)'.format(
                                        taxlevel = taxlevel,
                                        limit = args.cutoff,
                                        max = max_percent ),
              file = fh)
    else:
        # Heading
        print('\t'.join( [args.label] +
                         (["Total Reads"] if args.total_reads else []) +
                         mm.list_labels('taxon') ),
              file=fh)

        # Rows
        for lib in mm.list_labels('lib'):

            print('\t'.join( [lib] +
                             (["{:.0f}".format(total_reads_per_lib[lib])] if args.total_reads else []) +
                             [ "{:.{}f}".format(v, args.round) for v in mm.get_vector('lib', lib) ] ),
                  file=fh)

    # And done
    fh.close()

class Matrix:
    """A lightweight 2D matrix suitable for my porpoises.
       Yes I could use a Pandas DataFrame and copy the R logic but I don't see the need to
       depend on Pandas (which is big) and also I'd still need to define the sort/prune logic
       which is the trickiest bit of the code.
       See test_blob_matrix.py for example usage.
    """
    def __init__(self, colname='x', rowname='y', numsort=(),  empty=0.0):

        # What to call the axes, if not X and Y
        self._colname = colname
        self._rowname = rowname
        self._col_numsort = self._colname in numsort
        self._row_numsort = self._rowname in numsort
        self._empty = empty
        self._data = dict()

    def copy(self):
        # This works. I assume the stored values won't be mutable
        # types.
        return deepcopy(self)

    def add_overwrite(self, val, **kwargs):
        """Add a value to the matrix
        """
        if len(kwargs) > 2:
            # All other cases will trigger a KeyError below.
            raise IndexError("Too many kwargs")

        if type(val) != type(self._empty):
            raise TypeError("{} is not a {}".format(val, type(self._empty)))

        # I tried a defaultdict but it causes problems - ie.
        # if the caller tries to retrieve an unknown column it springs into
        # existence.
        self._data.setdefault(kwargs[self._colname], dict())[kwargs[self._rowname]] = val

    def add(self, val, **kwargs):
        """Add a value but check it's not already set.
           This is normally what we want.
        """
        if kwargs[self._rowname] in self._data.get(kwargs[self._colname], {}):
            raise KeyError

        self.add_overwrite(val, **kwargs)

    def list_labels(self, name):
        """List all the labels for either the rows or columns.
           Sort order will be depend on the order specified at object creation.
        """
        if name == self._colname:
            return self._list_col_labels()

        elif name == self._rowname:
            return self._list_row_labels()

        else:
            raise KeyError("The name may be {} or {}.", self._colname, self._rowname)

    def _scan_rowlabels(self):
        """Calculate all the row labels.
           If I cared at all about efficiency I'd keep the set stored, but I don't.
        """
        return set([ rl for cv in self._data.values() for rl in cv ])

    def _list_col_labels(self):
        rowlabels = self._scan_rowlabels()

        # Always sort by name first.
        res = sorted(self._data)

        if self._col_numsort:
            # The labels with the highest max values come first
            res.sort( reverse = True,
                      key = lambda cl:
                        max(self._data[cl].get(rl, self._empty) for rl in rowlabels) )

        return res

    def _list_row_labels(self):

        # Always sort by name first.
        res = sorted(self._scan_rowlabels())

        if self._row_numsort:
            res.sort( reverse = True,
                      key = lambda rl:
                        max(self._data[cl].get(rl, self._empty) for cl in self._data) )

        return res

    def prune(self, name, func):
        """Prune out rows or columns where no item passes the test.
           Note that empty cells are also checked.
            func : a function on type(this.empty) => bool
        """
        # Need this to correctly check empty values
        rowlabels = self._scan_rowlabels()

        if name == self._colname:
            # Scan through columns
            for cl in list(self._data):
                if not any( func(self._data[cl].get(rl, self._empty))
                            for rl in rowlabels ):
                    del self._data[cl]

        elif name == self._rowname:
            # Actually turns out to be simpler. Scan through rows
            for rl in rowlabels:
                if not any( func(self._data[cl].get(rl, self._empty))
                            for cl in self._data ):
                    for cl in self._data:
                        del self._data[cl][rl]

        else:
            raise KeyError("The name may be {} or {}.", self._colname, self._rowname)


    def get_vector(self, name, label):
        """Get a whole row or column
        """
        # Opposite to list_labels since to fetch a whole row I need the column
        # labels and vice versa.
        if name == self._colname:

            return [ self._data[label].get(rl, self._empty) for
                     rl in self._list_row_labels() ]

        elif name == self._rowname:
            return [ self._data[cl].get(label, self._empty) for
                     cl in self._list_col_labels() ]
        else:
            raise KeyError("The name may be {} or {}.", self._colname, self._rowname)

def parse_args(*args):
    description = """ Takes one or more .blobplot.stats.txt files and makes a TSV table
                      of the most common taxa by BAM (or COV) file.
                  """
    argparser = ArgumentParser( description=description,
                                formatter_class = ArgumentDefaultsHelpFormatter )
    argparser.add_argument("-o", "--output", default='-',
                            help="Where to save the result. Defaults to stdout.")
    argparser.add_argument("-c", "--cutoff", type=float, default="1.0",
                            help="Taxa found at less than cutoff%% in all samples will not be shown.")
    argparser.add_argument("-l", "--label", default="Library ID",
                            help="Label to put on the first column")
    argparser.add_argument("-t", "--total_reads", action="store_true",
                            help="Add a 'Total Reads' column.")
    argparser.add_argument("-r", "--round", type=int, default=2,
                            help="Number of decimals to keep in floats.")
    argparser.add_argument("statstxt", nargs="+",
                            help="One or more input files to scan.")
    argparser.add_argument("-d", "--debug", action="store_true",
                            help="Print more verbose debugging messages.")

    return argparser.parse_args(*args)

if __name__ == "__main__":
    main(parse_args())
