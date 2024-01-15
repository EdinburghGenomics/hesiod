#!/usr/bin/env python3

"""Test the functions in scan_cells.py, which used to be directly in Snakefile.main"""

import sys, os, re
import unittest
import logging
from pprint import pprint
from textwrap import dedent

import yaml

DATA_DIR = os.path.abspath(os.path.dirname(__file__) + '/examples')
VERBOSE = os.environ.get('VERBOSE', '0') != '0'

from scan_cells import ( scan_main, parse_args, scan_cells, sc_counts,
                         find_representative_fast5, find_representative_pod5 )

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
    def test_scan_cells(self):
        """ Test that scanning cells works with the new more complex logic.
              cell -> '.' -> 'fastX_pass' : [ list of files ]
        """
        res = scan_cells(f"{DATA_DIR}/runs/20190710_LOCALTEST_00newrun")
        sc = res['scanned_cells']

        self.assertEqual(sc, {'testlib/20190710_1723_2-A5-D5_PAD38578_c6ded78b' : { '.': {
                                       "bam_pass": [],
                                       "bam_fail": [],
                                       "pod5_pass": [],
                                       "pod5_fail": [],
                                       "fast5_fail": [],
                                       "fastq_fail": [],
                                       "fastq.gz_fail": [],
                                       "fast5_pass": ['testlib/20190710_1723_2-A5-D5_PAD38578_c6ded78b/fast5_pass/'
                                                        'PAD38578_ceefaf6d76ad8167a2c1050da8a9b3de9601f838_0.fast5',
                                                      'testlib/20190710_1723_2-A5-D5_PAD38578_c6ded78b/fast5_pass/'
                                                        'PAD38578_ceefaf6d76ad8167a2c1050da8a9b3de9601f838_1.fast5',
                                                      'testlib/20190710_1723_2-A5-D5_PAD38578_c6ded78b/fast5_pass/'
                                                        'PAD38578_ceefaf6d76ad8167a2c1050da8a9b3de9601f838_2.fast5'],
                                       "fastq_pass": ['testlib/20190710_1723_2-A5-D5_PAD38578_c6ded78b/fastq_pass/'
                                                        'PAD38578_ceefaf6d76ad8167a2c1050da8a9b3de9601f838_0.fastq',
                                                      'testlib/20190710_1723_2-A5-D5_PAD38578_c6ded78b/fastq_pass/'
                                                        'PAD38578_ceefaf6d76ad8167a2c1050da8a9b3de9601f838_1.fastq'],
                                       "fastq.gz_pass": ['testlib/20190710_1723_2-A5-D5_PAD38578_c6ded78b/fastq_pass/'
                                                           'PAD38578_ceefaf6d76ad8167a2c1050da8a9b3de9601f838_2.fastq.gz']
                                 } }})
        self.assertEqual(res['counts'], dict( cells=1, cellsaborted=0, cellsready=1 ))

    def test_scan_main(self):
        """ A test with a big experiment with muliple flowcells and barcodes and BAM
            files.
            Also this calls the main function so we expect a full output as if called
            on the command line.
        """
        args = parse_args([f"{DATA_DIR}/runs/20221103_EGS2_25070AT"])
        sc = scan_main( args )

        with open(f"{DATA_DIR}/runs/20221103_EGS2_25070AT/sc_data.yaml") as yfh:
            expected = yaml.safe_load(yfh)

        self.assertEqual(sc, expected)

    def test_scan_error(self):
        """ A missing fast5 file should raise an exception
        """
        # FIXME - how does this work with POD5?
        with self.assertRaises(RuntimeError):
            scan_cells( f"{DATA_DIR}/runs/20190710_LOCALTEST_00missingfile",
                        cellsready=['testlib/20190710_1723_2-A5-D5_PAD38578_c6ded78b'] )

    def test_scan_cells_bc(self):
        """ Scan the cells when there are barcodes. The pattern should be:
              cell -> barcode -> 'fastX_pass' : [ list of files ]
        """
        # 20210520_EGS1_16031BA/16031BApool01/20210520_1105_2-E1-H1_PAG23119_76e7e00f
        res1 = scan_cells( f"{DATA_DIR}/runs/20210520_EGS1_16031BA",
                           cellsready=['16031BApool01/20210520_1105_2-E1-H1_PAG23119_76e7e00f'] )
        sc1 = res1['scanned_cells']

        self.assertCountEqual(sc1, ['16031BApool01/20210520_1105_2-E1-H1_PAG23119_76e7e00f'])
        self.assertCountEqual( sc1['16031BApool01/20210520_1105_2-E1-H1_PAG23119_76e7e00f'],
                               [ 'barcode01', 'barcode02', 'barcode21', 'barcode22', 'unclassified' ] )
        self.assertEqual(res1['counts'], dict( cells=1, cellsaborted=0, cellsready=1 ))

        # Auto detecting the cells ready should produce the same result.
        res2 = scan_cells(f"{DATA_DIR}/runs/20210520_EGS1_16031BA")

        self.assertEqual(res1, res2)

    def test_find_representative_fast5_bc(self):
        """ Test the function that picks a fast5 file to probe for metadata
        """
        cell_name = '16031BApool01/20210520_1105_2-E1-H1_PAG23119_76e7e00f'
        sc = scan_cells( f"{DATA_DIR}/runs/20210520_EGS1_16031BA",
                         cellsready=[cell_name] )['scanned_cells']

        if VERBOSE:
            pprint(sc)

        self.assertEqual( find_representative_fast5(cell_name, sc[cell_name], try_glob=False),
                          f"{cell_name}/fast5_barcode01_pass/PAG23119_pass_barcode01_0eaeb70c_1.fast5" )

    def test_find_representative_fast5_nobc(self):
        """ And for the barcodeless version
        """
        cell_name = 'testlib/20190710_1723_2-A5-D5_PAD38578_c6ded78b'
        sc = scan_cells( f"{DATA_DIR}/runs/20190710_LOCALTEST_00newrun",
                         cellsready=[cell_name] )['scanned_cells']

        self.assertEqual( find_representative_fast5(cell_name, sc[cell_name], try_glob=False),
                          cell_name + "/fast5_._pass/PAD38578_ceefaf6d76ad8167a2c1050da8a9b3de9601f838_0.fast5" )

    def test_find_representative_fast5_null(self):
        """ Oh and the null version
        """
        empty_sc = { 'bc0' : { 'fastq_pass': [],
                               'fastq_fail': [],
                               'fast5_pass': [],
                               'fast5_fail': [] } }

        self.assertEqual( find_representative_fast5('foo', empty_sc, try_glob=False), None )

    def test_sc_counts(self):
        """ Test the function that prints a representation of the SC dict
        """
        sc =  {'testlib/testcell_123' : { '.': dict(
                       bam_fail   = [],
                       pod5_fail  = [],
                       fastq_fail = [],
                       pod5_pass  = ['testlib/testcell_123/pod5_pass/PAD38578_aaa_0.pod5',
                                     'testlib/testcell_123/pod5_pass/PAD38578_aaa_1.pod5'],
                       bam_pass   = ['testlib/testcell_123/bam_pass/PAD38578_aaa_0.bam',
                                     'testlib/testcell_123/bam_pass/PAD38578_aaa_1.bam'],
                       fast5_pass = ['testlib/testcell_123/fast5_pass/PAD38578_aaa_0.fast5',
                                     'testlib/testcell_123/fast5_pass/PAD38578_aaa_1.fast5'],
                       fastq_pass = ['testlib/testcell_123/fastq_pass/PAD38578_aaa_0.fastq',
                                     'testlib/testcell_123/fastq_pass/PAD38578_aaa_1.fastq'],
                    ) }}

        res = sc_counts(sc)

        # pformat sorts the dict keys alphabetically
        expected = """\
                      {'testlib/testcell_123': {'.': {'bam_fail': '<0 files>',
                                                      'bam_pass': '<2 files>',
                                                      'fast5_pass': '<2 files>',
                                                      'fastq_fail': '<0 files>',
                                                      'fastq_pass': '<2 files>',
                                                      'pod5_fail': '<0 files>',
                                                      'pod5_pass': '<2 files>'}}}
                   """
        expected = dedent(expected).rstrip()

        if VERBOSE:
            print("#" + res + "#")
            print("#" + expected + "#")
        self.assertEqual(res, expected)

        res2 = sc_counts(sc, width=80, show_zeros=False)
        expected2 = """\
                       {'testlib/testcell_123': {'.': {'bam_pass': '<2 files>',
                                                       'fast5_pass': '<2 files>',
                                                       'fastq_pass': '<2 files>',
                                                       'pod5_pass': '<2 files>'}}}
                    """
        expected2 = dedent(expected2).rstrip()

        if VERBOSE:
            print("#" + res2 + "#")
            print("#" + expected2 + "#")
        self.assertEqual(res2, expected2)


if __name__ == '__main__':
    unittest.main()
