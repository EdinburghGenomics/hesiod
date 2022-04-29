#!/usr/bin/env python3

"""Test the functions found in the Snakefile"""

import sys, os, re
import unittest
import logging
from itertools import takewhile
from pprint import pprint
from unittest.mock import Mock, patch
from tempfile import mkstemp
from textwrap import dedent as dd
from collections import OrderedDict

SNAKEFILE = os.path.abspath(os.path.dirname(__file__) + '/../Snakefile.main')
DATA_DIR = os.path.abspath(os.path.dirname(__file__) + '/examples')
VERBOSE = os.environ.get('VERBOSE', '0') != '0'

# other imports are synthesized by setUpClass below, but I have to declare them
# here to keep flake8 happy
scan_cells = '_importme'
sc_counts  = '_importme'
find_representative_fast5 = '_importme'
save_out_plist = '_importme'
get_cell_info = '_importme'
label_for_part = '_importme'

class T(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # So the thing is I don't want to take the functions out of the Snakefile
        # But I really want to test them. So we have this hack. Hackety hack.
        with open(SNAKEFILE) as sfh:
            # Chop out everything after "## End of functions ##"
            snake_code = list(takewhile(lambda l: not l.startswith("## End of functions ##"), sfh))
            snake_code = compile("".join(snake_code), sfh.name, 'exec')

        os.environ['TOOLBOX'] = 'NONE'
        os.environ['REFS'] = '.'
        gdict = dict( os = os,
                      workflow = Mock(snakefile='NONE'),
                      snakemake = Mock(),
                      config = dict() )
        exec(snake_code, gdict)
        #pprint(gdict)

        # Import to global namespace.
        funcs_to_import = [ k for k, v in globals().items() if v == "_importme" ]
        for func in funcs_to_import:
            globals()[func] = gdict[func]

        # Now we can fix the logging for the Snakefile functions which normally log
        # to the Snakemake logger.
        gdict['logger'] = logging.getLogger()
        gdict['logger'].setLevel(logging.DEBUG if VERBOSE else logging.CRITICAL)

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
        sc, counts = scan_cells( os.path.join(DATA_DIR, "runs/201907010_LOCALTEST_newrun"),
                                 dict() )

        self.assertEqual(sc, {'testlib/20190710_1723_2-A5-D5_PAD38578_c6ded78b' : { '.': {
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
        self.assertEqual(counts, dict( cells=1, cellsaborted=0, cellsready=1 ))

    def test_scan_error(self):
        """ A missing fast5 file should raise an exception
        """
        with self.assertRaises(RuntimeError):
            sc, counts = scan_cells( os.path.join(DATA_DIR, "runs/201907010_LOCALTEST_missingfile"),
                                     dict( cellsready='testlib/20190710_1723_2-A5-D5_PAD38578_c6ded78b' ) )

    def test_scan_cells_bc(self):
        """ Scan the cells when there are barcodes. The pattern should be:
              cell -> barcode -> 'fastX_pass' : [ list of files ]
        """
        # 20210520_EGS1_16031BA/16031BApool01/20210520_1105_2-E1-H1_PAG23119_76e7e00f
        sc1, counts1 = scan_cells( os.path.join(DATA_DIR, "runs/20210520_EGS1_16031BA"),
                                   dict( cellsready='16031BApool01/20210520_1105_2-E1-H1_PAG23119_76e7e00f' ) )

        self.assertCountEqual(sc1, ['16031BApool01/20210520_1105_2-E1-H1_PAG23119_76e7e00f'])
        self.assertCountEqual( sc1['16031BApool01/20210520_1105_2-E1-H1_PAG23119_76e7e00f'],
                               [ 'barcode01', 'barcode02', 'barcode21', 'barcode22', 'unclassified' ] )
        self.assertEqual(counts1, dict( cells=1, cellsaborted=0, cellsready=1 ))

        # Auto detecting the cells ready should produce the same result.
        sc2, counts2 = scan_cells( os.path.join(DATA_DIR, "runs/20210520_EGS1_16031BA"),
                                   dict() )

        self.assertEqual(sc1, sc2)
        self.assertEqual(counts1, counts2)

    def test_find_representative_fast5_bc(self):
        """ Test the function that picks a fast5 file to probe for metadata
        """
        cell_name = '16031BApool01/20210520_1105_2-E1-H1_PAG23119_76e7e00f'
        sc, counts = scan_cells( os.path.join(DATA_DIR, "runs/20210520_EGS1_16031BA"),
                                 dict( cellsready=cell_name ) )

        self.assertEqual( find_representative_fast5(cell_name, sc, try_glob=False),
                          cell_name + "/fast5_barcode01_pass/PAG23119_pass_barcode01_0eaeb70c_1.fast5" )

    def test_find_representative_fast5_nobc(self):
        """ And for the barcodeless version
        """
        cell_name = 'testlib/20190710_1723_2-A5-D5_PAD38578_c6ded78b'
        sc, counts = scan_cells( os.path.join(DATA_DIR, "runs/201907010_LOCALTEST_newrun"),
                                 dict( cellsready=cell_name ) )

        self.assertEqual( find_representative_fast5(cell_name, sc, try_glob=False),
                          cell_name + "/fast5_._pass/PAD38578_ceefaf6d76ad8167a2c1050da8a9b3de9601f838_0.fast5" )

    def test_find_representative_fast5_null(self):
        """ Oh and the null version
        """
        empty_sc = dict(foo = { 'bc0' : { 'fastq_pass': [],
                                          'fastq_fail': [],
                                          'fast5_pass': [],
                                          'fast5_fail': [] } })

        self.assertRaises( RuntimeError,
                           find_representative_fast5, 'foo', empty_sc, try_glob=False )

    def test_sc_counts(self):
        """ Test the function that prints a representation of the SC dict
        """
        sc =  {'testlib/testcell_123' : { '.': dict(
                       fast5_fail = [],
                       fastq_fail = [],
                       fast5_pass = ['testlib/testcell_123/fast5_pass/PAD38578_aaa_0.fast5',
                                     'testlib/testcell_123/fast5_pass/PAD38578_aaa_1.fast5'],
                       fastq_pass = ['testlib/testcell_123/fastq_pass/PAD38578_aaa_0.fastq',
                                     'testlib/testcell_123/fastq_pass/PAD38578_aaa_1.fastq'],
                    ) }}

        res = sc_counts(sc)

        # pformat sorts the dict keys alphabetically
        expected = """\
                      {'testlib/testcell_123': {'.': {'fast5_fail': '<0 files>',
                                                      'fast5_pass': '<2 files>',
                                                      'fastq_fail': '<0 files>',
                                                      'fastq_pass': '<2 files>'}}}
                   """
        expected = dd(expected).rstrip()

        if VERBOSE:
            print("#" + res + "#")
            print("#" + expected + "#")
        self.assertEqual(res, expected)

    def test_save_out_plist(self):
        # Pretty simple function but let's test it anyway

        yaml_files = [ f"{DATA_DIR}/cell_info/{f}_cell_info.yaml"
                       for f in [ 'one_cell_barcoded',
                                  'seven_cells_01',
                                  'seven_cells_02',
                                  'seven_cells_03', ] ]

        # temp file for output
        temp_fd, out_file = mkstemp()
        try:
            os.close(temp_fd)
            save_out_plist(yaml_files, out_file)

            # Read it back
            with open(out_file) as read_fh:
                self.assertEqual(read_fh.read(), "11608\n16031\n")

        finally:
            # Delete the temp file
            os.unlink(out_file)

    def test_label_for_part(self):
        # Not much to say about this. It just does a dict lookup
        self.assertEqual(label_for_part("eno"), "passed and control-mapping")
        self.assertEqual(label_for_part("eno", "barcode00"), "barcode00 control-mapping")

    def test_get_cell_info(self):
        """Just test the base case. We can add more if needed, of if bugs are suspected.
        """
        expected = { 'Experiment': "20220101_EGS1_12345AA",
                     'Cell': '12345AA0018/20220101_1234_1-A1-A1_AAA66666_deadbeef',
                     'Library': '12345AA0018',
                     'Date': '20220101',
                     'Number': '1234',
                     'Slot': '1-A1-A1',
                     'CellID': 'AAA66666',
                     'Checksum': 'deadbeef',
                     'Project': '12345',
                     'Base': '12345AA0018/20220101_1234_1-A1-A1_AAA66666_deadbeef/'
                             '20220101_EGS1_12345AA_12345AA0018_AAA66666_deadbeef',
                     'Files in pass': 'unknown',
                     'Files in fail': 1,
                     'Files in fast5 fail': 1,
                     '_counts': [
                        {'_barcode': '.', '_label': 'All passed reads', '_part': 'pass'},
                        {'_barcode': '.', '_label': 'Passed and lambda-filtered reads', '_part': 'nolambda'},
                        {'_barcode': '.', '_label': 'All failed reads', '_part': 'fail'} ],
                     '_blobs': ['../../__blob__'],
                     '_final_summary': {'is_rna': False},
                     '_nanoplot': '../../__nanoplot__',
                   }


        got = get_cell_info( experiment = "20220101_EGS1_12345AA",
                             cell = "12345AA0018/20220101_1234_1-A1-A1_AAA66666_deadbeef",
                             cell_content = { '.': dict( fast5_pass = ['x.fast5'],
                                                         fastq_fail = ['y.fastq'],
                                                         fast5_fail = ['y.fast5'] ) },
                             counts = { ('.','pass'): dict(),
                                        ('.','fail'): dict(),
                                        ('.','nolambda'): dict() },
                             fin_summary = dict(is_rna = False),
                             blobs = ['__blob__'],
                             nanoplot = '__nanoplot__',
                             fast5_meta = dict() )

        if VERBOSE:
            pprint(got)

        self.assertEqual( type(got), OrderedDict )
        self.assertEqual( dict(got), expected )

if __name__ == '__main__':
    unittest.main()
