#!/usr/bin/env python3

"""Check reading the metadata from a FAST5 file"""

# The file used, small2.fast5.gz, is from the gr dataset specifically the fail file.
# I removed all but one read and the signal to minimize the file size, then I repacked
# with h5repack and gzipped to make it teeny. Note this file has no Guppy version in
# the metadata.

import sys, os, re
import unittest
import logging
from collections import OrderedDict
from unittest.mock import Mock, patch

DATA_DIR = os.path.abspath(os.path.dirname(__file__) + '/examples')
VERBOSE = os.environ.get('VERBOSE', '0') != '0'

try:
    with patch('sys.path', new=['.'] + sys.path):
        from get_fast5_metadata import md_from_fast5_file
except:
    # If this fails, you is probably running the tests wrongly (or else there
    # is a syntax error in a script.)
    print("****",
          "To test your working copy of the code you should use the helper script:",
          "  ./run_tests.sh <name_of_test>",
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

    ### THE TESTS ###
    def test_small2(self):

        md = md_from_fast5_file(DATA_DIR + '/small2.fast5.gz')

        # Once we upgrade to Python 3.8 we can purge all OrderedDicts.
        self.assertEqual(type(md), OrderedDict)

        # Note this test will pass if md is a regular dict, even in Python 3.5 where
        # dict order is arbitrary.
        self.assertEqual(md, OrderedDict([
                    ('Fast5Version',      '1.0'),
                    ('StartTime',         'Monday, 18 Feb 2019 12:09:52'),
                    ('BaseCaller',        'MinKNOW-Live-Basecalling'),
                    ('BaseCallerTime',    'Monday, 18 Feb 2019 12:10:12'),
                    ('BaseCallerVersion', '3.1.18'),
                    ('RunID',             '94ab673ad12e5cc35f7110d9d285723b4aafdb68'),
                    ('ExperimentType',    'genomic_dna'),
                    ('SequencingKit',     'sqk-lsk109'),
                    ('FlowcellType',      'flo-pro002'),
        ]) )

if __name__ == '__main__':
    unittest.main()
