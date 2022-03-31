#!/usr/bin/env python3

"""Test stuff in hesiod/__init__.py"""

# Note this will get discovered and run as a no-op test. This is fine.

import sys, os, re
import unittest
import logging
from datetime import datetime, timezone
from dateutil.tz.tz import tzutc
from pprint import pprint

DATA_DIR = os.path.abspath(os.path.dirname(__file__) + '/examples')
VERBOSE = os.environ.get('VERBOSE', '0') != '0'

from hesiod import parse_cell_name, load_final_summary, abspath, groupby

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
    def test_parse_cell_name(self):

        res = parse_cell_name('20210520_EGS1_16031BA', '16031BApool01/20210520_1105_2-E1-H1_PAG23119_76e7e00f')
        self.assertEqual(dict(res), dict(
                    Run       = '20210520_EGS1_16031BA',
                    Cell      = '16031BApool01/20210520_1105_2-E1-H1_PAG23119_76e7e00f',
                    Library   = '16031BApool01',
                    Date      = '20210520',
                    Number    = '1105',
                    Slot      = '2-E1-H1',
                    CellID    = 'PAG23119',
                    Checksum  = '76e7e00f',
                    Project   = '16031',
                    Base      = '16031BApool01/20210520_1105_2-E1-H1_PAG23119_76e7e00f/'
                                  '20210520_EGS1_16031BA_16031BApool01_PAG23119_76e7e00f' ) )

    def test_load_final_summary(self):

        example_file = os.path.join(DATA_DIR, "final_summary_PAK00383_564d5253.txt")

        # The datetime comparison needs to use tzutc() even though timezone.utc is functionally equivalent,
        # because of the way datetutil operates.

        self.assertEqual( load_final_summary(example_file),
                          dict( instrument          = "PCT0112",
                                position            = "2-E11-H11",
                                flow_cell_id        = "PAK00383",
                                sample_id           = "21600MP_2_0001-0004",
                                protocol_group_id   = "21600MP_2",
                                protocol            = "sequencing/sequencing_PRO002_DNA:FLO-PRO002:SQK-LSK109",
                                protocol_run_id     = "f8320272-62ba-4f8d-821a-fb3dffcde338",
                                acquisition_run_id  = "564d52535b8db9cd5a084b612eed13cc68eaf349",
                                started             = datetime(2022, 3, 2, 13, 21, 2, 322037, tzinfo=tzutc()),
                                acquisition_stopped = datetime(2022, 3, 3, 14, 53, 9, 611224, tzinfo=tzutc()),
                                processing_stopped  = datetime(2022, 3, 3, 14, 53, 14, 662014, tzinfo=tzutc()),
                                basecalling_enabled = True,
                                sequencing_summary_file   = "sequencing_summary_PAK00383_564d5253.txt",
                                fast5_files_in_final_dest = 3126,
                                fast5_files_in_fallback   = 0,
                                fastq_files_in_final_dest = 3125,
                                fastq_files_in_fallback   = 0 ) )

    def test_abspath(self):

        self.assertEqual( abspath('/tmp', relative_to='/proc'), '/tmp')

        self.assertEqual( abspath('null', relative_to='/dev/random'), '/dev/null')

    def test_groupby(self):

        fruits = "apple apricot durian cherry banana ambarella blueberry bilberry".split()

        self.assertEqual( dict(groupby(fruits, lambda f: f[0])),
                          dict( a = ['apple', 'apricot', 'ambarella'],
                                d = ['durian'],
                                c = ['cherry'],
                                b = ['banana', 'blueberry', 'bilberry'] ) )

        self.assertEqual( dict(groupby(fruits, lambda f: f[0], sort_by_key=True)),
                          dict( a = ['apple', 'apricot', 'ambarella'],
                                b = ['banana', 'blueberry', 'bilberry'],
                                c = ['cherry'],
                                d = ['durian'] ))

        def some_sort_func(l):
            return dict((v,k) for k,v in enumerate("badc"))[l]

        self.assertEqual( list(groupby(fruits, lambda f: f[0], sort_by_key=some_sort_func)),
                          list("badc") )


if __name__ == '__main__':
    unittest.main()
