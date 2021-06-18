#!/usr/bin/env python3

"""Test stuff in hesiod/__init__.py"""

# Note this will get discovered and run as a no-op test. This is fine.

import sys, os, re
import unittest
import logging
from pprint import pprint

DATA_DIR = os.path.abspath(os.path.dirname(__file__) + '/examples')
VERBOSE = os.environ.get('VERBOSE', '0') != '0'

from hesiod import parse_cell_name, abspath, groupby

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
