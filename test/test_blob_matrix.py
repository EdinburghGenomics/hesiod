#!/usr/bin/env python3

"""Test the matrix class used in parse_blob_template.py"""

import sys, os, re
import unittest
import logging
from unittest.mock import Mock

VERBOSE = os.environ.get('VERBOSE', '0') != '0'

from parse_blob_table import Matrix

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

        # Don't invert order of axes in cheese matrix
        self.invert = False

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

        # This actually works but probably should raise KeyError?
        self.assertEqual(m.get_vector('x', 'notset'), [])
        self.assertEqual(m.get_vector('y', 'notset'), [])

    def test_bad_get(self):

        m = Matrix(empty=-1)

        # Trying to get data from unknown labels is a bad idea, as the
        # results are inconsistent. See above.
        m.add(1, x='foo', y='bar')
        with self.assertRaises(KeyError):
            m.get_vector('x', 'notset')
        self.assertEqual(m.get_vector('y', 'notset'), [-1])

        # These should fail.
        with self.assertRaises(KeyError):
            m.add_overwrite(1, x='foo', z='moo')
        with self.assertRaises(IndexError):
            m.add_overwrite(1, x='foo', y='bar', z='moo')

    def test_bad_type(self):

        # Can only add items that match the type of the empty value
        m = Matrix()
        with self.assertRaises(TypeError):
            m.add_overwrite(1, x='foo', y='bar')

        # Empty is integer
        m2 = Matrix(empty=0)
        m2.add_overwrite(1, x='foo', y='bar')
        with self.assertRaises(TypeError):
            m2.add_overwrite(0.1, x='foo', y='bar')

        # Empty is string
        m3 = Matrix(empty='')
        m3.add_overwrite('1.0', x='foo', y='bar')
        with self.assertRaises(TypeError):
            m3.add_overwrite(0.1, x='foo', y='bar')

    def test_double_add(self):

        # It's useful to check that we only add things once. When combining blob
        # reports we don't expect to see the same pieve of info twice, unless there
        # is an error in the input.
        m = Matrix()
        m.add(1.0, x='foo', y='bar')

        with self.assertRaises(KeyError):
            m.add(2.0, x='foo', y='bar')

        # But we can force it.
        m.add_overwrite(2.0, x='foo', y='bar')

    def cheese(self, **kwargs):
        # Give me a chees matrix to play with (hey, why not?)
        if self.invert:
            # Switching rows and cols should have no effect
            m = Matrix('quality', 'cheese', **kwargs)
        else:
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
        m2 = m.copy()
        m2.prune('cheese', lambda s: s >= 9.0)

        self.assertEqual(m2.list_labels('cheese'),
                         ["Cheshire", "Danish"])
        self.assertEqual(m2.get_vector(axis='quality', label='crumbliness'),
                         [9.0, 4.0])
        self.assertEqual(m2.get_vector(axis='quality', label='strength'),
                         [2.0, 9.0])

        # Now just the extreme lows. Ie . Cheshire for flavour strength
        m3 = m.copy()
        m3.prune('cheese', lambda s: s <= 2.0)
        self.assertEqual(m3.list_labels('cheese'), ["Cheshire"])

        # Or if nothing passes the test
        m3.prune('cheese', lambda s: s <= 1.0)
        self.assertEqual(m3.list_labels('cheese'), [])

    def test_basic_inverted(self):
        self.invert = True
        self.test_basic()

    def test_sort(self):
        # Now make it so that both columns and rows sort by highest first
        m = self.cheese(numsort=['cheese', 'quality'])

        # Now the item with the max value comes first. Then alphabetical. Like top trumps.
        self.assertEqual(m.list_labels('cheese'), ["Cheshire", "Danish", "Wensleydale"])
        self.assertEqual(m.list_labels('quality'), ["crumbliness", "strength", "firmness"])

        # Data should come out accordingly
        self.assertEqual(m.get_vector('cheese', 'Cheshire'), [9.0, 2.0, 6.0])
        self.assertEqual(m.get_vector('quality', 'strength'), [2.0, 9.0, 5.0])

    def test_sort_inverted(self):
        self.invert = True
        self.test_sort()

    def test_copy(self):
        # Just to be sure the copy constructor works properly
        m = self.cheese()

        # Make a copy and wipe it out
        m2 = m.copy()
        m2.prune('cheese', lambda x: False)
        self.assertEqual(m2.list_labels('cheese'), [])
        self.assertEqual(m2.list_labels('quality'), ["crumbliness", "firmness", "strength"])
        m2.prune('quality', lambda x: False)
        self.assertEqual(m2.list_labels('quality'), [])

        # And again but in the opposite order
        m3 = m.copy()
        m3.prune('quality', lambda x: False)
        self.assertEqual(m3.list_labels('cheese'), ["Cheshire", "Danish", "Wensleydale"])
        self.assertEqual(m3.list_labels('quality'), [])
        m3.prune('cheese', lambda x: False)
        self.assertEqual(m3.list_labels('cheese'), [])

        # But m is still intact?
        self.assertEqual(len(m.list_labels('cheese')), 3)
        self.assertEqual(len(m.list_labels('quality')), 3)

    def test_copy_inverted(self):
        self.invert = True
        self.test_copy()

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

        # Prune to see only qualities with some item missing. All cheeses have been rated for
        # firmness and strength.
        m2 = m.copy()
        m2.prune('quality', lambda s: s == 0.0)

        self.assertEqual(m2.list_labels('quality'), ["crumbliness", "gooeyness"])
        # Now with the strength and firmess ratings gone the sort order changes...
        self.assertEqual(m2.list_labels('cheese'), ["Cheshire", "Brie", "Wensleydale", "Danish"])

    def test_sparse_inverted(self):
        self.invert = True
        self.test_sparse()

    def test_sparse_2(self):
        """See bug discussed in doc/run_20191107_EGS1_11921LK0002.txt
           Pruning on one axis must not remove items from the other axis.
        """

        # As above, use the standard cheeses and add Brie with only firmness=1.0
        m = self.cheese(numsort=['cheese'])
        m.add(1.0, cheese="Brie", quality="firmness")
        self.assertEqual(m.list_labels('cheese'), ["Cheshire", "Danish", "Wensleydale", "Brie"])
        self.assertEqual(m.list_labels('quality'), ["crumbliness", "firmness", "strength"])

        # Now prune the dataset so firmness vanishes, but we still want to see Brie in the
        # list of cheeses. (Max firmness is 7.0)
        m.prune('quality', lambda s: s >= 8.0)

        self.assertEqual(m.list_labels('quality'), ["crumbliness", "strength"])
        self.assertEqual(m.list_labels('cheese'), ["Cheshire", "Danish", "Wensleydale", "Brie"])

        # Should be the same if I'd added a parameter not shared with the other cheeses.
        m2 = self.cheese(numsort=['cheese'])
        m2.add(5.0, cheese="Brie", quality="smelliness")
        self.assertEqual(m2.list_labels('cheese'), ["Cheshire", "Danish", "Wensleydale", "Brie"])
        self.assertEqual(m2.list_labels('quality'), ["crumbliness", "firmness", "smelliness", "strength"])

        # Now prune the dataset so firmness and smelliness vanish, but we still want to see Brie in the
        # list of cheeses. (Max firmness is 7.0)
        m2.prune('quality', lambda s: s >= 8.0)

        self.assertEqual(m2.list_labels('quality'), ["crumbliness", "strength"])
        self.assertEqual(m2.list_labels('cheese'), ["Cheshire", "Danish", "Wensleydale", "Brie"])

    def test_sparse_2_inverted(self):
        self.invert = True
        self.test_sparse_2()

if __name__ == '__main__':
    unittest.main()
