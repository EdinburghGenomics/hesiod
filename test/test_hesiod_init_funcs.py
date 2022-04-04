#!/usr/bin/env python3

"""Template/boilerplate for writing new test classes"""

# Note this will get discovered and run as a no-op test. This is fine.

import sys, os, re
import unittest
import logging
from unittest.mock import Mock, patch # if needed

DATA_DIR = os.path.abspath(os.path.dirname(__file__) + '/examples')
VERBOSE = os.environ.get('VERBOSE', '0') != '0'

from hesiod import glob

class T(unittest.TestCase):

    def setUp(self):
        # See the errors in all their glory
        self.maxDiff = None

    def test_glob(self):
        # Sort order in glob() results is important for consistency, but the numbered files produced
        # in fastq_pass and fast5_pass are like:
        #   fastq_pass/PAK01183_pass_bda16547_0.fastq.gz
        #   fastq_pass/PAK01183_pass_bda16547_1.fastq.gz
        #   fastq_pass/PAK01183_pass_bda16547_10.fastq.gz
        #   fastq_pass/PAK01183_pass_bda16547_100.fastq.gz
        # So we need a numeric order sort to keep them in proper order.
        glob_test_dir = os.path.join(DATA_DIR, "glob_test")
        assert os.path.exists(glob_test_dir)

        self.assertEqual( glob(glob_test_dir + "/*.dat"),
                          [ glob_test_dir + "/AAA.dat",
                            glob_test_dir + "/xxx.dat" ] )

        self.assertEqual( [ os.path.basename(f) for f in  glob(glob_test_dir + "/*.fastq.gz") ],
                          """PAK01183_fail_bda16547_0.fastq.gz
                             PAK01183_fail_bda16547_5.fastq.gz
                             PAK01183_fail_bda16547_10.fastq.gz
                             PAK01183_fail_bda16547_100.fastq.gz
                             PAK01183_fail_bda16547_101.fastq.gz
                             PAK01183_pass_bda16547_0.fastq.gz
                             PAK01183_pass_bda16547_5.fastq.gz
                             PAK01183_pass_bda16547_14.fastq.gz
                             PAK01183_pass_bda16547_20.fastq.gz
                             PAK01183_pass_bda16547_69.fastq.gz
                             PAK01183_pass_bda16547_100.fastq.gz
                             PAK01183_pass_bda16547_701.fastq.gz
                          """.split() )

        self.assertEqual( [ os.path.basename(f) for f in  glob(glob_test_dir + "/*") ],
                          """AAA.dat
                             PAK01183_fail_bda16547_0.fastq.gz
                             PAK01183_fail_bda16547_5.fastq.gz
                             PAK01183_fail_bda16547_10.fastq.gz
                             PAK01183_fail_bda16547_100.fastq.gz
                             PAK01183_fail_bda16547_101.fastq.gz
                             PAK01183_pass_bda16547_0.fastq.gz
                             PAK01183_pass_bda16547_5.fastq.gz
                             PAK01183_pass_bda16547_14.fastq.gz
                             PAK01183_pass_bda16547_20.fastq.gz
                             PAK01183_pass_bda16547_69.fastq.gz
                             PAK01183_pass_bda16547_100.fastq.gz
                             PAK01183_pass_bda16547_701.fastq.gz
                             xxx.dat
                          """.split() )


if __name__ == '__main__':
    unittest.main()
