#!/usr/bin/env python3

"""Test some parts of the report maker"""

import sys, os, re
import unittest
import logging
from unittest.mock import Mock, patch

DATA_DIR = os.path.abspath(os.path.dirname(__file__) + '/examples')
VERBOSE = os.environ.get('VERBOSE', '0') != '0'

try:
    with patch('sys.path', new=['.'] + sys.path):
        from make_report import list_projects
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
        self.maxDiff = None

    def tearDown(self):
        pass

    ### THE TESTS ###
    def test_list_projects(self):
        """This function takes a list of cells and returns a list of triples
           (name, label, [cells]).
           It's similar to the generic groupby() function, but with extra processing
           specific to the cell/project.
        """
        # For our purposes each 'cell' needs only a Project.
        projnames = "11608 11650 11650 11650000XXX 11609".split()
        cells = [ {'Project': n} for n in projnames ]

        # Empty input
        self.assertEqual(list_projects(cells[:0], None), [])

        # Input with no supporting dict
        self.assertEqual(list_projects(cells, None), [
                                ('11608', 'Project 11608', [{'Project': '11608'}]),
                                ('11609', 'Project 11609', [{'Project': '11609'}]),
                                ('11650', 'Project 11650', [{'Project': '11650'},{'Project': '11650'}]),
                                ('11650000XXX', 'Project 11650000XXX', [{'Project': '11650000XXX'}]), ])

        # If a dict is supplied we should add names and links
        realnames = { '11608' : { 'name' : '11608_Test_Test',
                                  'url'  : 'http://foo' },
                      '11650' : { 'name' : '11650_Test2_Test2' } }

        self.assertEqual(list_projects(cells[:1], realnames), [
                                ('11608', 'Project [11608_Test_Test](http://foo)', [{'Project': '11608'}]), ])

        self.assertEqual(list_projects(cells, realnames), [
                                ('11608', 'Project [11608_Test_Test](http://foo)', [{'Project': '11608'}]),
                                ('11609', 'Project 11609', [{'Project': '11609'}]),
                                ('11650', 'Project 11650_Test2_Test2', [{'Project': '11650'},{'Project': '11650'}]),
                                ('11650000XXX', 'Project 11650000XXX', [{'Project': '11650000XXX'}]), ])

    def test_array_slice(self):
        """At present this doesn't test any code. I just want to check my logic.
        """

        # Three files (aka cells) with three counts in each
        cell1 = dict( _counts= [ dict( _label = "cat1",
                                       total  = 100 ),
                                 dict( _label = "cat2",
                                       total  = 200 ),
                                 dict( _label = "cat3",
                                       total  = 300 ) ] )

        cell2 = dict( _counts= [ dict( _label = "cat1",
                                       total  = 110 ),
                                 dict( _label = "cat2",
                                       total  = 220 ),
                                 dict( _label = "cat3",
                                       total  = 330 ) ] )

        cell3 = dict( _counts= [ dict( _label = "cat1",
                                       total  = 111 ),
                                 dict( _label = "cat2",
                                       total  = 222 ),
                                 dict( _label = "cat3",
                                       total  = 333 ) ] )

        all_cells = [cell1, cell2, cell3]
        all_counts = [ c['_counts'] for c in all_cells ]

        # So now I need to generate a sum for cat1
        sum_cat1 = sum( c[0]['total'] for c in all_counts )
        self.assertEqual(sum_cat1, 321)

        # Now I need to generate a sum/min/max for cat1
        stats_cat1 = ( sum( c[0]['total'] for c in all_counts ),
                       min( c[0]['total'] for c in all_counts ),
                       max( c[0]['total'] for c in all_counts ) )
        self.assertEqual(stats_cat1, (321, 100, 111))

        # Now I need to generate the same for all categories and label them
        labels = [ f['_label'] for f in all_counts[0] ]
        stats_table = [ ( label,
                          sum( c[row]['total'] for c in all_counts ),
                          min( c[row]['total'] for c in all_counts ),
                          max( c[row]['total'] for c in all_counts ) )
                        for row, label in enumerate(labels) ]
        #self.assertEqual(stats_table, [])

        # This works nicely, but is there any way to remove the repeats of c[row]?
        # Within the expansion, we only care about one row, so:
        stats_table2= [ ( label,
                          sum( cc['total'] for cc in cat_counts ),
                          min( cc['total'] for cc in cat_counts ),
                          max( cc['total'] for cc in cat_counts ) )
                        for row, label in enumerate(labels)
                        for cat_counts in [[c[row] for c in all_counts]] ]
        self.assertEqual(stats_table2, stats_table)

        # Getting there, but we still have the 'for cc in cat_counts' part repeated.
        # Can't I get rid of this by making cat_counts a dict of lists? Given that
        # we only care about 'total' here...
        stats_table3= [ ( label,
                          sum( cat_counts['total'] ),
                          min( cat_counts['total'] ),
                          max( cat_counts['total'] ) )
                        for row, label in enumerate(labels)
                        for cat_counts in [{ k: [ c[row][k] for c in all_counts ]
                                             for k in ['total'] }] ]
        self.assertEqual(stats_table3, stats_table)

        # Yeah that's it! I can add any keys I like to the list.

if __name__ == '__main__':
    unittest.main()
