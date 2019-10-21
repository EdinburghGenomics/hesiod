#!/usr/bin/env python3

"""Test the matrix class used in parse_blob_template.py"""

# Note this will get discovered and run as a no-op test. This is fine.

import sys, os, re
import unittest
import logging
from unittest.mock import Mock, patch

VERBOSE = os.environ.get('VERBOSE', '0') != '0'

try:
    with patch('sys.path', new=['.'] + sys.path):
        from parse_blob_table import Matrix
except:
    #If this fails, you is probably running the tests wrongly
    print("****",
          "To test your working copy of the code you should use the helper script:",
          "  ./run_tests.sh blob_matrix",
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

    ### THE TESTS ###
    def test_nop(self):

        m = Matrix()

        # A matrix with no rows or columns and no data. The column labels should be
        # 'x' and the row labels should be 'y'
        self.assertEqual(m._colname, 'x')
        self.assertEqual(m._rowname, 'y')

        self.assertEqual(m.list_labels('x'), [])

        # This actually works but maybe should raise KeyError?
        self.assertEqual(m.get_vector('x', 'notset'), [])

    def cheese(self, **kwargs):
        # Give me a chees matrix to play with
        m = Matrix('cheese', 'quality', **kwargs)


        m.add(5.0, cheese="Wensleydale", quality="strength")
        m.add(6.0, cheese="Wensleydale", quality="crumbliness")
        m.add(7.0, cheese="Wensleydale", quality="firmness")
        m.add(2.0, cheese="Cheshire",    quality="strength")
        m.add(9.0, cheese="Cheshire",    quality="crumbliness")
        m.add(6.0, cheese="Cheshire",    quality="firmness")
        m.add(9.0, cheese="Danish",      quality="strength")
        m.add(4.0, cheese="Danish",      quality="crumbliness")
        m.add(4.0, cheese="Danish",      quality="firmness")

        return m

    def test_basic(self):

        m = self.cheese()

        self.assertEqual(m.list_labels('cheese'), ["Cheshire", "Danish", "Wensleydale"])
        self.assertEqual(m.list_labels('quality'), ["crumbliness", "firmness", "strength"])

        self.assertEqual(m.get_vector('cheese', 'Cheshire'), [9.0, 6.0, 2.0])
        self.assertEqual(m.get_vector('quality', 'strength'), [2.0, 9.0, 5.0])

        # Only look at the 'extreme' cheeses with some score >=9.0. Ie. Danish for stength
        # and Wensleydale for crumbliness.
        self.assertEqual(m.list_labels('cheese', lambda s: s >= 9.0),
                         ["Cheshire", "Danish"])
        self.assertEqual(m.get_vector('quality', 'crumbliness', lambda s: s >= 9.0),
                         [9.0, 4.0])
        self.assertEqual(m.get_vector('quality', 'strength', lambda s: s >= 9.0),
                         [2.0, 9.0])

        # Now just the extreme lows. Ie . Cheshire for flavour strength
        self.assertEqual(m.list_labels('cheese', lambda s: s <= 2.0),
                                 ["Cheshire"])

        # Or if nothing passes the test
        self.assertEqual(m.list_labels('cheese', lambda s: s <= 1.0),
                                 [])

    def test_sort(self):
        # Now make it so that both columns and rows sort by highest first
        m = self.cheese(numsort=['cheese', 'quality'])

        # Now the item with the max value comes first. Then alphabetical. Like top trumps.
        self.assertEqual(m.list_labels('cheese'), ["Cheshire", "Danish", "Wensleydale"])
        self.assertEqual(m.list_labels('quality'), ["crumbliness", "strength", "firmness"])

        # Data should come out accordingly
        self.assertEqual(m.get_vector('cheese', 'Cheshire'), [9.0, 2.0, 6.0])
        self.assertEqual(m.get_vector('quality', 'strength'), [2.0, 9.0, 5.0])

    def test_sparse(self):

        m = self.cheese(numsort=['cheese'])

        # For brie we only have firmness
        # The cheese should come last
        m.add(1.0, cheese="Brie",      quality="firmness")
        self.assertEqual(m.list_labels('cheese'), ["Cheshire", "Danish", "Wensleydale", "Brie"])

        # Now make it a really smelly brie and it comes first
        m.add(10.0, cheese="Brie",      quality="strength")
        self.assertEqual(m.list_labels('cheese'), ["Brie", "Cheshire", "Danish", "Wensleydale"])

        # Give it a quality that nothing else has
        m.add(8.0, cheese="Brie",      quality="gooeyness")

        # Qualities should still be in alphabetical order
        self.assertEqual(m.list_labels('quality'), ["crumbliness", "firmness", "gooeyness", "strength"])

        # And getting vectors should still be fine
        self.assertEqual(m.get_vector('quality', 'crumbliness'),
                         [0.0, 9.0, 4.0, 6.0])
        self.assertEqual(m.get_vector('quality', 'strength'),
                         [10.0, 2.0, 9.0, 5.0])
        self.assertEqual(m.get_vector('quality', 'gooeyness'),
                         [8.0, 0.0, 0.0, 0.0])

        self.assertEqual(m.get_vector('cheese', 'Brie'),
                         [0.0, 1.0, 8.0, 10.0])
        self.assertEqual(m.get_vector('cheese', 'Wensleydale'),
                         [6.0, 7.0, 0.0, 5.0])

if __name__ == '__main__':
    unittest.main()
