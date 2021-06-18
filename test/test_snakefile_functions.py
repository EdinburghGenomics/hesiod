#!/usr/bin/env python3

"""Test the functions found in the Snakefile"""

import sys, os, re
import unittest
import logging
from itertools import takewhile
from pprint import pprint
from unittest.mock import Mock, patch

SNAKEFILE = os.path.abspath(os.path.dirname(__file__) + '/../Snakefile.main')
DATA_DIR = os.path.abspath(os.path.dirname(__file__) + '/examples')
VERBOSE = os.environ.get('VERBOSE', '0') != '0'

# other imports are synthesized by setUpClass below, but I have to declare them
# here to keep flake8 happy
scan_cells = '_importme'
sc_counts  = '_importme'

def fixstr(s_in):
    """Sort out a multi-line string
    """
    s_lines = s_in.splitlines(True)

    # Indent is length of last line + 3, because it is
    # Discard the last line
    indent = len(s_lines.pop()) + 3

    # Strip all but the first line
    for n, l in list(enumerate(s_lines))[1:]:
        s_lines[n] = l[indent:]

    # If first line is blank, discard it
    if not re.search('\S', s_lines[0]):
        s_lines[0:1] = []

    return "".join(s_lines).rstrip("\n")

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
        # In this example no cells are ready but we see ther is one cell
        self.assertEqual(sc, dict())
        self.assertEqual(counts, dict( cells=1, cellsaborted=0, cellsready=0 ))

        # If we say that the cell is ready we should detect the files
        sc, counts = scan_cells( os.path.join(DATA_DIR, "runs/201907010_LOCALTEST_newrun"),
                                 dict( cellsready='testlib/20190710_1723_2-A5-D5_PAD38578_c6ded78b' ) )
        self.assertEqual(sc, {'testlib/20190710_1723_2-A5-D5_PAD38578_c6ded78b' : { '.': dict(
                                       fast5_fail = [],
                                       fastq_fail = [],
                                       fast5_pass = ['testlib/20190710_1723_2-A5-D5_PAD38578_c6ded78b/fast5_pass/'
                                                       'PAD38578_ceefaf6d76ad8167a2c1050da8a9b3de9601f838_0.fast5',
                                                     'testlib/20190710_1723_2-A5-D5_PAD38578_c6ded78b/fast5_pass/'
                                                       'PAD38578_ceefaf6d76ad8167a2c1050da8a9b3de9601f838_1.fast5'],
                                       fastq_pass = ['testlib/20190710_1723_2-A5-D5_PAD38578_c6ded78b/fastq_pass/'
                                                       'PAD38578_ceefaf6d76ad8167a2c1050da8a9b3de9601f838_0.fastq',
                                                     'testlib/20190710_1723_2-A5-D5_PAD38578_c6ded78b/fastq_pass/'
                                                       'PAD38578_ceefaf6d76ad8167a2c1050da8a9b3de9601f838_1.fastq'],
                                 ) }})
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
        expected = """{'testlib/testcell_123': {'.': {'fast5_fail': '<0 files>',
                                                      'fast5_pass': '<2 files>',
                                                      'fastq_fail': '<0 files>',
                                                      'fastq_pass': '<2 files>'}}}
                   """

        if VERBOSE:
            print("#" + res + "#")
            print("#" + fixstr(expected) + "#")
        self.assertEqual(res, fixstr(expected))

if __name__ == '__main__':
    unittest.main()
