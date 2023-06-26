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

DATA_DIR = os.path.abspath(os.path.dirname(__file__) + '/examples')
VERBOSE = os.environ.get('VERBOSE', '0') != '0'

from get_fast5_metadata import md_from_fast5_file

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

        expected = OrderedDict([
                    ('Fast5Version',      '1.0'),
                    ('StartTime',         'Monday, 18 Feb 2019 12:09:52'),
                    ('RunID',             '94ab673ad12e5cc35f7110d9d285723b4aafdb68'),
                    ('ExperimentType',    'genomic_dna'),
                    ('SequencingKit',     'sqk-lsk109'),
                    ('BasecallConfig',    'dna_r9.4.1_450bps_prom.cfg'),
                    ('SamplingFrequency', '4 kHz'), ])

        # Note a standard equality test will pass if md is a regular dict, even in Python 3.5 where
        # dict order is arbitrary. So check the keys explicitly.
        # And comparing two OrderedDicts does not yield a readable diff, so compare the two
        # as dictionaies.
        self.assertEqual(list(md), list(expected))
        self.assertEqual(dict(md), dict(expected))

    def test_v2_3(self):
        """Try a newer FAST5 file
        """

        md = md_from_fast5_file(DATA_DIR + '/PAK00002_fail_barcode07_b7f7032d_0.fast5.gz')

        expected = dict( Fast5Version      = '2.3',
                         StartTime         = 'Tuesday, 01 Mar 2022 15:38:47',
                         GuppyVersion      = '5.1.13+b292f4d',
                         RunID             = 'b7f7032d28779ac6666af1b4fd724bf2ec41ec25',
                         ExperimentType    = 'genomic_dna',
                         SequencingKit     = 'sqk-lsk109',
                         BasecallConfig    = 'dna_r9.4.1_450bps_hac_prom.cfg',
                         SamplingFrequency = '4 kHz', )

        self.assertEqual(list(md), list(expected))
        self.assertEqual(dict(md), dict(expected))

if __name__ == '__main__':
    unittest.main()
