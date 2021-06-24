#!/usr/bin/env python3

"""Tests for parse_blob_table.py
   Mainly to see if the new script output matches the old, of which
   we have many examples.
"""

import sys, os, re
import unittest
import logging
from io import StringIO
from unittest.mock import Mock, MagicMock, patch, call, mock_open, DEFAULT

DATA_DIR = os.path.abspath(os.path.dirname(__file__) + '/blobplot_stats')
VERBOSE = os.environ.get('VERBOSE', '0') != '0'

from parse_blob_table import main as parse_main
from parse_blob_table import name_extractor_hesiod

def fp_mock_open(filepattern='.*', **kwargs):
    """A version of the standard mock_open that only mocks when filepattern
       matches the given pattern.
    """
    mo_obj = mock_open(**kwargs)
    filepattern = filepattern.rstrip("$") + '$'

    # capture open() in a closure now before any patching can happen
    real_open = open

    def new_call(filename, *args, **kwargs):
        if not re.match(filepattern, filename):
            return real_open(filename, *args, **kwargs)
        else:
            return DEFAULT

    # Patch the mo_obj and return it
    mo_obj.side_effect = new_call
    return mo_obj


class T(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        #Prevent the logger from printing messages - I like my tests to look pretty.
        if VERBOSE:
            logging.getLogger().setLevel(logging.DEBUG)
        else:
            logging.getLogger().setLevel(logging.CRITICAL)

    def setUp(self):
        # See the errors in all their glory
        self.maxDiff = None

    def tearDown(self):
        pass

    def def_args(self):
        # Default args to pass to main
        return  Mock( cutoff = 1.0,
                      label = "Library ID",
                      total_reads = False,
                      debug = False,
                      output = 'MOCK_OUT',
                      name_extractor = "regular",
                      round = 2 )

    def check_with_csv(self, infiles, outfile, **kwargs):
        """Check that the new script makes the same output as the old.
           Note that the old version didn't sort the rows, so I've manually fixed this
           in the sample CSV files. It doesn't matter as datatables.js re-does the sort in
           the browser anyway.
           Also the old code (deliberately!) doesn't recalculate percentages on the 'other'
           row, but I can't see why. I've checked and fixed the numbers in the CSV samples.
           Finally, Jon's code represents 2.10 as 2.1. I am correct, of course.
        """

        args = self.def_args()

        for k, v in kwargs.items():
            setattr(args, k, v)

        args.statstxt = infiles

        # Load the outfile and convert commas to tabs
        # If the file was already TSV this works too.
        with open(outfile) as fh:
            outlines = [ l.rstrip('\n').replace(',', '\t') for l in fh ]

        # Parse the infile
        inlines = self.run_main(args)

        # Inspect the result
        self.assertEqual(inlines, outlines)

    def run_main(self, args):

        # I was patching sys.stdout here with a MagicMock but this breaks interactive
        # debugging and potentially hides any printed messages.
        # So instead let's mock out the open() func instead.
        omock = fp_mock_open(filepattern="MOCK_OUT")
        with patch('parse_blob_table.open', omock):
            parse_main(args)
        dummy_stdout = omock

        # File should have been closed.
        self.assertEqual(dummy_stdout.mock_calls[-1], call().close())

        # Reconstruct what was 'written' to the mock...
        return ''.join([ txt for n,a,k in dummy_stdout.mock_calls
                         if n == '().write'
                         for txt in a ]).rstrip('\n').split('\n')

    ### THE TESTS ###
    def test_name_extractor(self):
        """Test the new name extractor
           Not sure if this is ideal but the original names were getting too long.
        """
        self.assertEqual( name_extractor_hesiod("## cov0=/lustre-gseg/home/tbooth2/test_promethion/fastqdata/"
                                                "20210520_EGS1_16031BA/.snakemake/shadow/tmp2q8pn8nb/blob/"
                                                "16031BApool01/20210520_1105_2-E1-H1_PAG23119_76e7e00f/"
                                                "20210520_EGS1_16031BA_16031BApool01_PAG23119_76e7e00f_barcode02_pass+sub10000.complexity"),
                          "16031BApool01 PAG23119_76e7e00f barcode02" )

        self.assertEqual( name_extractor_hesiod("## cov0=/lustre-gseg/home/tbooth2/test_promethion/fastqdata/"
                                                "20210520_EGS1_16031BA/.snakemake/shadow/tmp2q8pn8nb/blob/"
                                                "16031BApool01/20210520_1105_2-E1-H1_PAG23119_76e7e00f/"
                                                "20210520_EGS1_16031BA_16031BApool01_PAG23119_76e7e00f_._pass+sub10000.complexity"),
                          "16031BApool01 PAG23119_76e7e00f" )

        # If the script parses an old file with nop barcode it shouldn't get confused
        self.assertEqual( name_extractor_hesiod("cov0=blob/11921LK0002L01/20191108_1522_2-A3-D3_PAE00889_c16432d0/"
                                                "20191107_EGS1_11921LK0002_11921LK0002L01_PAE00889_c16432d0_pass+sub10000.complexity"),
                          "11921LK0002L01 PAE00889_c16432d0" )

    def test_noop(self):
        """No-op behaviour
        """
        args = self.def_args()
        args.statstxt = []
        res = self.run_main(args)

        self.assertEqual(res, ["No taxon is represented by at least 1.0% of reads (max None%)"])

    def test_empty(self):
        """And with no useful data
        """
        args = self.def_args()
        args.statstxt = [DATA_DIR + '/other/empty.blobplot.stats.txt']
        res = self.run_main(args)

        self.assertEqual(res, ["No empty is represented by at least 1.0% of reads (max None%)"])

    def test_nothing_within_cutoff(self):
        """This goes along with test_20190405_EGS1_11650KL but when there is nothing to show.
        """
        testdir = DATA_DIR + '/20190405_EGS1_11650KL/'
        statstxt = testdir + '20190405_EGS1_11650KL_11608GE0009_PAD41410_pass.order.blobplot.stats.txt'

        # Using the Hesiod file with cutoff set to 60 we get nothing
        "No order is represented by at least 60.0% of reads (max 57.77%)"

        self.check_with_csv( [ statstxt ],
                             testdir + 'cutoff60.csv',
                             cutoff = 60.0 )

        # If the round is set to 0 then we should get a slightly different message
        "No order is represented by at least 60.0% of reads (max 57%)"

        self.check_with_csv( [ statstxt ],
                             testdir + 'cutoff60round0.csv',
                             cutoff = 60.0,
                             round = 0 )


    def test_11760(self):
        """Some files from project 11760
        """
        for t in "phylum order species".split():

            basename = DATA_DIR + '/all_11760/all_11760'

            self.check_with_csv( ['{}.{}.blobplot.stats.txt'.format(basename, t)],
                                  '{}.{}.csv'.format(basename, t) )

    def test_11889_unmap(self):
        """Much like the one above but this has three files to input.
        """
        testdir = DATA_DIR + '/unmap_11889'

        statstxt = [ "{}/11889SA{}L01.order.blobplot.stats.txt".format(testdir, n)
                     for n in ['0001', '0002', '0003'] ]

        self.check_with_csv( statstxt,
                             testdir + '/blobstats.order.Unmapped.csv' )


    def test_20190405_EGS1_11650KL(self):
        """Some 'jellyfish plot' data from Hesiod
        """
        testdir = DATA_DIR + '/20190405_EGS1_11650KL/'
        statstxt = testdir + '20190405_EGS1_11650KL_11608GE0009_PAD41410_pass.order.blobplot.stats.txt'

        self.check_with_csv( [ statstxt ],
                             testdir + 'regular.csv' )

        self.check_with_csv( [ statstxt ],
                             testdir + 'cutoff0.02.csv',
                             cutoff = 0.02 )

        self.check_with_csv( [ statstxt ],
                             testdir + 'withtotal.csv',
                             total_reads = True
                             )

        self.check_with_csv( [ statstxt ],
                             testdir + 'labelfoo.csv',
                             label = 'Foo'
                             )

        # Diplaying 4DP just gives extra zeros here because there are 10000 reads
        self.check_with_csv( [ statstxt ],
                             testdir + 'round4.csv',
                             round = 4
                             )

    def test_20191107_EGS1_11921LK0002(self):
        """Issues seen in Hesiod.
           See doc/run_20191107_EGS1_11921LK0002.txt for info on what went wrong here.
           Note that check_with_csv works on the TSV files too.
        """
        testdir = DATA_DIR + '/20191107_EGS1_11921LK0002/'
        tmpl = testdir + '20191107_EGS1_11921LK0002_{}_pass.{}.blobplot.stats.txt'

        for p_o_s in "phylum order species".split():
            self.check_with_csv( [ tmpl.format('11921LK0002L01_PAE00889_c16432d0', p_o_s),
                                   tmpl.format('11921LK0002L02_PAE00889_65ecf29b', p_o_s),
                                   tmpl.format('11921LK0002_PAE00889_eb80ac83', p_o_s) ],
                                 '{}blobstats.11921.pass.{}.tsv'.format(testdir, p_o_s),
                                 total_reads = True,
                                 name_extractor = 'hesiod',
                                 label = 'Cell' )

    def test_with_barcodes(self):
        """After processing a run with barcodes I get a KeyError.
           Not sure if the input data is valid but I should get a better error
           at least.
        """
        testdir = DATA_DIR + '/20210520_EGS1_16031BA_barcoded/'
        tmpl = testdir + 'barcode{}_pass.phylum.blobplot.stats.txt'

        self.check_with_csv( [ tmpl.format("01"), tmpl.format("02") ],
                             testdir + "blobstats_pass.phylum.tsv",
                             total_reads = True,
                             cutoff = 0.5,
                             name_extractor = 'hesiod',
                             label = 'Cell' )

if __name__ == '__main__':
    unittest.main()
