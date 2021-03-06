#!/usr/bin/env python3

"""Test for make_summary.py which makes a little textual summary
   of a run to go on the RT ticket.
"""


import sys, os, re
import unittest
import logging
from unittest.mock import Mock, patch

DATA_DIR = os.path.abspath(os.path.dirname(__file__) + '/examples')
VERBOSE = os.environ.get('VERBOSE', '0') != '0'

try:
    with patch('sys.path', new=['.'] + sys.path):
        # from lib_or_script import functions
        from make_summary import format_table, scan_cells
except:
    #If this fails, you is probably running the tests wrongly
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
        pass

    def tearDown(self):
        pass

    ### THE TESTS ###
    def test_format_table_nop(self):
        """One row, no columns!"""
        res = format_table([], [[]])
        self.assertEqual(res, ['', '', ''])

    def test_format_table_basic(self):
        res = format_table("foo bar baz".split(), ["123", "456"])
        self.assertEqual(res[0], " foo       | bar       | baz" )
        self.assertEqual(res[1], "-----------|-----------|-----------" )
        self.assertEqual(res[2], " 1         | 2         | 3" )
        self.assertEqual(res[3], " 4         | 5         | 6" )

    def test_format_table_tw(self):
        res = format_table( "foo bar baz".split(),
                            ["123", ["something", "something", "dark side"]],
                            [10,7,3])
        self.assertEqual(res[0], " foo       | bar    | baz" )
        self.assertEqual(res[1], "-----------|--------|----" )
        self.assertEqual(res[2], " 1         | 2      | 3" )
        self.assertEqual(res[3], " something | somethi| dark side" )

    def test_format_table_onecol(self):
        res = format_table( "foo".split(),
                            [ ["123"], ["something or other"] ])
        self.assertEqual(res[0], " foo" )
        self.assertEqual(res[1], "-----------" )
        self.assertEqual(res[2], " 123" )
        self.assertEqual(res[3], " something or other" )

    def test_scan_cells(self):
        """Test the cell scan function on a sample dir.
           Normally driver.sh pass in the list explicitly in order to include remote unsynced cells
        """
        self.assertEqual( scan_cells(DATA_DIR + '/runs/20000101_TEST_testrun2'),
                          [ 'a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa',
                            'a test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb' ]
                        )

if __name__ == '__main__':
    unittest.main()
