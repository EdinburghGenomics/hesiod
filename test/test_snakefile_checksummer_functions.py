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

SNAKEFILE = os.path.abspath(os.path.dirname(__file__) + '/../Snakefile.checksummer')
VERBOSE = os.environ.get('VERBOSE', '0') != '0'

# other imports are synthesized by setUpClass below, but I have to declare them
# here to keep flake8 happy
split_input_dir = '_importme'
batchlist = '_importme'
scan_for_batches = '_importme'

class T(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # So the thing is I don't want to take the functions out of the Snakefile
        # But I really want to test them. So we have this hack. Hackety hack.
        with open(SNAKEFILE) as sfh:
            # Chop out everything after "## End of functions ##"
            snake_code = list(takewhile(lambda l: not l.startswith("## End of functions ##"), sfh))
            snake_code = compile("".join(snake_code), sfh.name, 'exec')

        gdict = dict( os = os,
                      workflow = Mock(snakefile='NONE'),
                      snakemake = Mock(),
                      config = dict(input_dir='.') )
        exec(snake_code, gdict)
        #pprint(gdict)

        # Import to global namespace.
        funcs_to_import = [ k for k, v in globals().items() if v == "_importme" ]
        for func in funcs_to_import:
            globals()[func] = gdict[func]

        # Now we can fix the logging for Snakefile functions which normally log
        # to the Snakemake logger.
        gdict['logger'] = logging.getLogger()
        gdict['logger'].setLevel(logging.DEBUG if VERBOSE else logging.CRITICAL)

    def setUp(self):
        # See the errors in all their glory
        self.maxDiff = None

    def tearDown(self):
        pass

    ### THE TESTS ###
    def test_split_input_dir(self):

        self.assertEqual( split_input_dir("basic/path"),
                          ("basic/path", "") )

        self.assertEqual( split_input_dir("/another/basic//path/"),
                          ("/another/basic//path", "") )

        self.assertEqual( split_input_dir("/basic/./path/right/here/right/./now"),
                          ("/basic/./path/right/here/right", "now") )

        # This was producing weird beviour without an extra check
        self.assertEqual( split_input_dir("/basic/path/right/here/."),
                          ("/basic/path/right/here/.", "") )

    def test_batchlist(self):

        l = "abcdefghijklmnopqrstuvwxyz"

        b1 = batchlist(l, 2, min_pad=1)
        self.assertEqual(b1, { '00': ['a', 'n'],
                               '01': ['b', 'o'],
                               '02': ['c', 'p'],
                               '03': ['d', 'q'],
                               '04': ['e', 'r'],
                               '05': ['f', 's'],
                               '06': ['g', 't'],
                               '07': ['h', 'u'],
                               '08': ['i', 'v'],
                               '09': ['j', 'w'],
                               '10': ['k', 'x'],
                               '11': ['l', 'y'],
                               '12': ['m', 'z'], })

        b2 = batchlist(l[:13], 4, min_pad=4)
        self.assertEqual(b2, { '0000': ['a', 'e', 'i', 'm'],
                               '0001': ['b', 'f', 'j'],
                               '0002': ['c', 'g', 'k'],
                               '0003': ['d', 'h', 'l'], })

if __name__ == '__main__':
    unittest.main()
