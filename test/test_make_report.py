#!/usr/bin/env python3

"""Test some parts of the report maker"""

import sys, os, re
import unittest
from unittest.mock import patch
import logging
from glob import glob
from textwrap import dedent as dd
import pickle
from pprint import pprint

DATA_DIR = os.path.abspath(os.path.dirname(__file__) + '/examples')
VERBOSE = os.environ.get('VERBOSE', '0') != '0'

from make_report import ( list_projects, format_counts_per_cells, load_cell_yaml, load_yaml,
                          abspath, escape_md, aggregator, get_cell_summary, resolve_filter )

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
    def test_aggregator(self):
        """Aggregator is a handy thing that behaves like this...
        """
        P = aggregator('')

        P('foo', 'bar')
        P()
        P(100)

        self.assertEqual('='.join(P), "=foo=bar==100")

        # This should be equivalent, and yield a copy of P._list
        self.assertEqual(list([*P]), list(P))

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
                                ('11608', 'Project 11608_Test_Test\n\n[\u21D2 Go to project page](http://foo)', [{'Project': '11608'}]), ])

        self.assertEqual(list_projects(cells, realnames), [
                                ('11608', 'Project 11608_Test_Test\n\n[\u21D2 Go to project page](http://foo)', [{'Project': '11608'}]),
                                ('11609', 'Project 11609', [{'Project': '11609'}]),
                                ('11650', 'Project 11650_Test2_Test2', [{'Project': '11650'},{'Project': '11650'}]),
                                ('11650000XXX', 'Project 11650000XXX', [{'Project': '11650000XXX'}]), ])

    def test_format_counts_per_cells(self):
        """Test the new logic that makes the Read Summary table in Stats Per Project
        """
        # For an old run with seven cells, no barcodes
        seven_cells = [ load_cell_yaml(f) for f in glob(DATA_DIR + "/cell_info/seven_cells_??_cell_info.yaml") ]

        self.assertEqual( format_counts_per_cells(seven_cells, heading="FOO"),
                          dd("""\
                                ### FOO

                                | Part | Total Reads | Total Bases | Max Length |
                                |------|-------------|-------------|------------|
                                | All passed reads | 15488849 | 198731265339 | 217472 |
                                | Lambda\-filtered passed reads | 12266134 | 187067423308 | 217472 |
                                | All failed reads | 8181438 | 28788689895 | 240324 |
                             """) )

        # For a new run with one cell, several barcodes
        bc_cell = [ load_cell_yaml(DATA_DIR + "/cell_info/one_cell_barcoded_cell_info.yaml") ]

        self.assertEqual( format_counts_per_cells(bc_cell, heading="BAR"),
                          dd("""\
                                ### BAR

                                | Part | Total Reads | Total Bases | Max Length |
                                |------|-------------|-------------|------------|
                                | All passed reads | 120134 | 130966011 | 11541 |
                                | Passed and lambda\-filtered reads | 120134 | 130966011 | 11541 |
                                | All failed reads | 120106 | 123147574 | 354311 |
                             """) )

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
        # Note this also works but then I can't add other keys than 'total'...
        stats_table4= [ ( label,
                          sum( total_counts ),
                          min( total_counts ),
                          max( total_counts ) )
                        for row, label in enumerate(labels)
                        for total_counts in ([c[row]['total'] for c in all_counts],) ]
        self.assertEqual(stats_table4, stats_table)


    def test_get_cell_summary(self):

        yaml_file = DATA_DIR + "/cell_info/18701TK0001_cell_info.yaml"
        yaml_info = load_cell_yaml(yaml_file)

        # Load in the NanoPlot data
        yaml_info['_nanoplot_data'] = load_yaml(abspath( yaml_info['_nanoplot'],
                                                         relative_to = yaml_file ))

        # We'll just use this single cell to test with
        all_info = { "18701TK0001/20220315_1458_2-E1-H1_PAI99791_06ff254e":
                     yaml_info }

        cs_headings, cs_rows = get_cell_summary(all_info)

        self.assertEqual(list(cs_headings), [ "Experiment Name",
                                              "Pool Name",
                                              "UUID",
                                              "Flow Cell ID",
                                              "Run Length",
                                              "Reads Generated (M)",
                                              "Estimated Bases (Gb)",
                                              "Passed Bases (Gb)",
                                              "Estimated N50 (kb)" ])
        self.assertEqual(len(cs_rows), 1)
        self.assertEqual(list(cs_rows[0]), [ "18701TK0001",
                                             "18701TK0001",
                                             "06ff254e-c2e1-4b07-a7de-5c240124386c",
                                             "PAI99791",
                                             "72 hours",
                                             "2.48",
                                             "2.58",
                                             "2.23",
                                             "1.36" ])

    @unittest.skip("Function was removed")
    def test_load_and_resolve_barcodes(self):
        # As noted in the code, this function is a bit ugly.
        # What I need to do is:
        # 1 - serialise the full all_info from project 20221103_EGS2_25070AT
        # 2 - keep re-parsing it because this function mutates the info
        # 3 - patch make_report.load_yaml to force loading from test dir
        # 4 - then I can test various cases

        # Set up the data structure
        def get_four_cells(cache=[]):
            if not cache:
                four_cells = {}
                for f in glob(DATA_DIR + "/20221103_EGS2_25070AT_cell_yaml/cell_info_?.yaml"):
                    y = load_cell_yaml(f)
                    #y['_nanoplot'] = abspath(y['_nanoplot'], relative_to=f)
                    #y['_nanoplot_data'] = load_yaml(y['_nanoplot'])
                    four_cells[y['Cell']] = y
                cache.append(pickle.dumps(four_cells))
            return pickle.loads(cache[0])

        # load_and_resolve_barcodes(filter, all_info, cutoff=0.01)

        # Basic tests that don't actually modify the result
        four_cells = get_four_cells()
        self.assertEqual(len(four_cells), 4)
        self.assertEqual( load_and_resolve_barcodes('all', four_cells), 'all')
        self.assertEqual( load_and_resolve_barcodes('none', four_cells), 'none')
        self.assertEqual( load_and_resolve_barcodes('wibble', {}), 'none')

        # This should see that there is only one used barcode in each cell.
        four_cells = get_four_cells()
        self.assertEqual( load_and_resolve_barcodes('cutoff', four_cells), 'cutoff')
        self.assertTrue( all([ '_filter_yaml' not in v for v in four_cells.values() ]) )
        self.assertEqual( set(four_cells), { '25070AT0003/20221103_1710_1F_PAM83464_136e9f68',
                                             '25070AT0003/20221104_1306_1G_PAM78534_6623d643',
                                             '25070AT0004/20221103_1710_1D_PAM83454_1f1b14bd',
                                             '25070AT0005/20221103_1710_1B_PAM82832_3ed26d0e' } )
        self.assertEqual( four_cells['25070AT0003/20221103_1710_1F_PAM83464_136e9f68']['_filter'],
                          {'barcode03': 'barcode03'} )
        self.assertEqual( four_cells['25070AT0003/20221104_1306_1G_PAM78534_6623d643']['_filter'],
                          {'barcode03': 'barcode03'} )
        self.assertEqual( four_cells['25070AT0004/20221103_1710_1D_PAM83454_1f1b14bd']['_filter'],
                          {'barcode04': 'barcode04'} )
        self.assertEqual( four_cells['25070AT0005/20221103_1710_1B_PAM82832_3ed26d0e']['_filter'],
                          {'barcode05': 'barcode05'} )

        # Cells 0 and 3 have valid sample_names.yaml files but we have to fudge where they are loaded
        # from.
        def _load_yaml(filepath):
            return load_yaml(filepath, relative_to=DATA_DIR + "/20221103_EGS2_25070AT_cell_yaml/_")

        four_cells = get_four_cells()
        del four_cells['25070AT0003/20221104_1306_1G_PAM78534_6623d643']
        del four_cells['25070AT0004/20221103_1710_1D_PAM83454_1f1b14bd']
        with patch('make_report.load_yaml', new=_load_yaml):
            self.assertEqual( load_and_resolve_barcodes('yaml', four_cells), 'yaml')
        self.assertEqual( four_cells['25070AT0003/20221103_1710_1F_PAM83464_136e9f68']['_filter'],
                          {'barcode01': '25070AT0001',
                           'barcode02': '25070AT0002',
                           'barcode03': '25070AT0003'} )
        self.assertEqual( four_cells['25070AT0005/20221103_1710_1B_PAM82832_3ed26d0e']['_filter'],
                          {'barcode05': '25070AT0005'} )


        # And for a mixture of valid/invalid
        four_cells = get_four_cells()
        with patch('make_report.load_yaml', new=_load_yaml):
            self.assertEqual( load_and_resolve_barcodes('yaml', four_cells), 'mixed')
        self.assertEqual( four_cells['25070AT0003/20221103_1710_1F_PAM83464_136e9f68']['_filter'],
                          {'barcode01': '25070AT0001',
                           'barcode02': '25070AT0002',
                           'barcode03': '25070AT0003'} )
        self.assertEqual( four_cells['25070AT0003/20221104_1306_1G_PAM78534_6623d643']['_filter'],
                          {'barcode03': 'barcode03'} )
        self.assertEqual( four_cells['25070AT0004/20221103_1710_1D_PAM83454_1f1b14bd']['_filter'],
                          {'barcode04': 'barcode04'} )
        self.assertEqual( four_cells['25070AT0005/20221103_1710_1B_PAM82832_3ed26d0e']['_filter'],
                          {'barcode05': '25070AT0005'} )



    def test_escape_md(self):
        # Double backslash is the most confusing.
        self.assertEqual( escape_md(r'\ '), r'\\ ')

        # And all the rest
        self.assertEqual( escape_md(r'<[][\`*_{}()#+-.!>'),
                          r'\<\[\]\[\\\`\*\_\{\}\(\)\#\+\-\.\!\>' )

if __name__ == '__main__':
    unittest.main()
