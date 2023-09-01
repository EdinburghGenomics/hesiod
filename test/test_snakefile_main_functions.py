#!/usr/bin/env python3

"""Test the functions found in the main Snakefile"""

import sys, os, re
import unittest
import logging
from itertools import takewhile
from pprint import pprint
from unittest.mock import Mock, patch
from tempfile import mkstemp
from collections import OrderedDict

SNAKEFILE = os.path.abspath(os.path.dirname(__file__) + '/../Snakefile.main')
DATA_DIR = os.path.abspath(os.path.dirname(__file__) + '/examples')
VERBOSE = os.environ.get('VERBOSE', '0') != '0'

# other imports are synthesized by setUpClass below, but I have to declare them
# here to keep flake8 happy
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
                     'Pool': '12345AA0018',
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
                        {'_barcode': '.', '_label': 'All passed reads', '_part': 'pass', 'total_reads': 200},
                        {'_barcode': '.', '_label': 'Passed and lambda-filtered reads', '_part': 'nolambda'},
                        {'_barcode': '.', '_label': 'All failed reads', '_part': 'fail'} ],
                     '_blobs': ['../../__blob__'],
                     '_duplex' : [ ['Duplex pairs',             1],
                                   ['from total passing reads', 200],
                                   ['% of passing reads',       '1.00%'] ],
                     '_filter_type': 'none',
                     '_final_summary': {'is_rna': False},
                     '_nanoplot': '../../__nanoplot__',
                   }


        got = get_cell_info( experiment = "20220101_EGS1_12345AA",
                             cell = "12345AA0018/20220101_1234_1-A1-A1_AAA66666_deadbeef",
                             cell_content = { '.': dict( fast5_pass = ['x.fast5'],
                                                         fastq_fail = ['y.fastq'],
                                                         fast5_fail = ['y.fast5'] ) },
                             counts = { ('.','pass'): dict(total_reads = 200),
                                        ('.','fail'): dict(),
                                        ('.','nolambda'): dict() },
                             fin_summary = dict(is_rna = False),
                             blobs = ['__blob__'],
                             nanoplot = '__nanoplot__',
                             duplex = 1,
                             fast5_meta = dict() )

        if VERBOSE:
            pprint(got)

        self.assertEqual( type(got), OrderedDict )
        self.assertEqual( dict(got), expected )

if __name__ == '__main__':
    unittest.main()
