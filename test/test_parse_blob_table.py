#!/usr/bin/env python3

"""Tests for parse_blob_table.py
   Mainly to see if the new script output matches the old, of which
   we have may examples.
"""

# Note this will get discovered and run as a no-op test. This is fine.

import sys, os, re
import unittest
import logging
from io import StringIO
from unittest.mock import Mock, MagicMock, patch, call

DATA_DIR = os.path.abspath(os.path.dirname(__file__) + '/blobplot_stats')
VERBOSE = os.environ.get('VERBOSE', '0') != '0'

try:
    with patch('sys.path', new=['.'] + sys.path):
        from parse_blob_table import main as parse_main
except:
    #If this fails, you is probably running the tests wrongly
    print("****",
          "To test your working copy of the code you should use the helper script:",
          "  ./run_tests.sh parse_blob_table",
          "or to run all tests, just",
          "  ./run_tests.sh",
          "****",
          sep="\n")
    raise

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
                      output = '-',
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
        with open(outfile) as fh:
            outlines = [ l.rstrip('\n').replace(',', '\t') for l in fh ]

        # Parse the infile
        inlines = self.run_main(args)

        # Inspect the result
        self.assertEqual(inlines, outlines)

    def run_main(self, args):

        # Patching sys.stdout with a StringIO object is no good since main() closes the FH,
        # and the content is dropped, and I can't mock the close() method of the builtin
        # type. Oh well - MagicMock to the rescue.
        dummy_stdout = MagicMock()
        with patch('sys.stdout', dummy_stdout):
            parse_main(args)

        # File should have been closed.
        self.assertEqual(dummy_stdout.close.mock_calls, [call()])

        # Reconstruct what was 'written' to the mock...
        return  ''.join([ mc[1][0] for mc in
                          dummy_stdout.write.mock_calls ]).rstrip('\n').split('\n')

    ### THE TESTS ###
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

if __name__ == '__main__':
    unittest.main()
