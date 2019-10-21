#!/usr/bin/env python3

""" Reimplementation of Jon's parseBlobTable.R in Python, because I can't be having with R.
    Results should be byte-identical with Jon's old code.
    See http://gitlab.genepool.private/production-team/qc_tools_python/blob/master/scripts/parseBlobTable.R
"""

import os, sys, re
import logging as L
from copy import deepcopy
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
        if not l:
            # Not expecting blank lines, but skip them if seen.
            continue
        if l.startswith('## '):
            headerlines.append(l[3:])
        elif l.startswith('# '):
            assert not colnames # Should only see one such line
            colnames = l[3:].split("\t")
        else:
            datalines.append(l.split("\t"))
            assert len(datalines[-1]) == len(colnames)

    # Now extract a name mapping dict from the headerlines and apply it to colnames
    name_map = { l.split('=')[0] : re.sub('(\+.*|\.[^.]*)$', '', l.split('/')[-1])
                 for l in headerlines
                 if re.match(r'(bam|cov)[0-9]+=', l) }

    '''
    # Drop the columns we don't need before doing the renaming
    # This removes a corner case in the old code where samples with the substring 'covsum'
    # anywhere in the name simply vanish from the results.
    col_filter = [ n == 'name' or ( n.split('_', 1) in name_map )
                   for n in colnames ]

    # Now we can munge and filter the names
    colnames2 = [ "{}_{}".format(name_map[nsplit[0]], nsplit[1])
                    if (nsplit[1:] and nsplit[0] in name_map) else n
                  for n, f in zip(colnames, col_filter)
                  for nsplit in [n.split('_', 1)]
                  if f ]

    # Apply the same filter to the data rows.
    # Yes I could do this more succinctly with pandas. No I don't want to.
    datalines2 = [ [ x for x, f in zip(dl, col_filter) if f ]
                   for dl in datalines ]
    '''
    # Coerce every value in a _read_map column to an integer, and each _read_map_p
    # column to a float
    for dl in datalines:
        for i, colname in enumerate(colnames):
            if colname.endswith('_read_map'):
                dl[i] = int(dl[i].replace(',',''))
            elif colname.endswith('_read_map_p'):
                dl[i] = float(dl[i].replace('%',''))

    return (colnames, name_map, datalines)

def main(args):

    L.basicConfig(level=(L.DEBUG if args.debug else L.WARNING))

    # Do all the parsing first. The tables won't be large so having everything in
    # memory at once is fine.
    all_tables = []
    for f in args.statstxt:
        with open(f) as fh:
            all_tables.append(read_blob_table(fh))



    for colnames, name_map, datalines in all_tables:

        # Since I'm not using a table datatype, make an index of the column names
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
        total_reads_per_lib = dict()
        for n in name_map:
            total_reads_per_lib[n] = (all_row[colidx[n+'_read_map']] * 100) / all_row[colidx[n+'_read_map_p']]


        # Now recalculate all the percentages relative to this value.
        for dl in datalines:
            for i, colname in enumerate(colnames):
                if colname.endswith('_read_map_p'):
                    total_reads = total_reads_per_lib[colname.split('_')[0]]
                    mapped_reads = dl[colidx[colname.split('_')[0]+'_read_map']]
                    new_pct = (mapped_reads * 100) / total_reads
                    # The new value should be close to the old one.
                    assert abs(dl[i] - new_pct) < 0.1
                    dl[i] = new_pct

        # Strip out rows that have name in ['all', 'no-hit', 'undef', 'other']
        datalines = [ dl for dl in datalines
                      if dl[colidx['name']] not in ['all', 'no-hit', 'undef', 'other'] ]

class Matrix:
    """A lightweight 2D matrix suitable for my porpoises.
       Yes I could use a Pandas DataFrame but I don't see the need to depend on Pandas
       (which is big) and also I'd still need to define the sort/prune logic which is the
       trickiest bit of the code.
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
        # This works.
        return deepcopy(self)

        c = super(Matrix, self)( self._colname,
                                 self._rowname,
                                 empty = self._empty )

        c._col_numsort = self._col_numsort
        c._row_numsort = self._row_numsort

        c._data = deepcopy(self._data)

    def add(self, val, **kwargs):
        """Add a value to the matrix
        """
        if len(kwargs) > 2:
            # All other cases will trigger a KeyError below.
            raise IndexError("Too many kwargs")

        # I tried a defaultdict but it causes problems - ie.
        # if the caller tries to retrieve an unknown column it springs into
        # existence.
        self._data.setdefault(kwargs[self._colname], dict())[kwargs[self._rowname]] = val

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
    description = """ Takes one or more .blobplot.stats.txt files and makes a CSV table
                      of the most common taxa by BAM (or COV) file.
                  """
    argparser = ArgumentParser( description=description,
                                formatter_class = ArgumentDefaultsHelpFormatter )
    argparser.add_argument("-o", "--output", default='-',
                            help="Where to save the result. Defaults to stdout.")
    argparser.add_argument("-c", "--cutoff", type=float, default="1.0",
                            help="Taxa found at less than cutoff% in all samples will not be shown.")
    argparser.add_argument("statstxt", nargs="+",
                            help="One or more input files to scan.")
    argparser.add_argument("-d", "--debug", action="store_true",
                            help="Print more verbose debugging messages.")

    return argparser.parse_args(*args)

if __name__ == "__main__":
    main(parse_args())
