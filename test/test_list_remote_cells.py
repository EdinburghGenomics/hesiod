#!/usr/bin/env python3

import unittest
import sys, os, re
from unittest.mock import patch

import subprocess
from tempfile import mkdtemp
from shutil import rmtree, copytree
from glob import glob

"""BinMocker is really overkill for testing this script, but I'll still use it as my
   standard way for testing shell scripts.
"""
from test.binmocker import BinMocker


VERBOSE = os.environ.get('VERBOSE', '0') != '0'
EXAMPLES = os.path.dirname(__file__) + '/examples'
SCRIPT = os.path.abspath(os.path.dirname(__file__) + '/../list_remote_cells.sh')

PROGS_TO_MOCK = {'ssh': None}

class T(unittest.TestCase):

    def setUp(self):
        self.bm = BinMocker()
        for p, s in PROGS_TO_MOCK.items(): self.bm.add_mock(p, side_effect=s)

        self.environment = dict()

        # See the errors in all their glory
        self.maxDiff = None

    def tearDown(self):
        """Clean up the BinMocker
        """
        self.bm.cleanup()

    def test_nop(self):
        """If UPSTREAM_LOC is not set it should be an error.
           If UPSTREAM_LOC is set to '' we should get nothing back.
        """
        bm = self.bm
        retval = bm.runscript(SCRIPT, set_path=False, env=self.environment)
        self.assertEqual(retval, 1)

        self.environment['UPSTREAM_LOC'] = ''
        retval = bm.runscript(SCRIPT, set_path=False, env=self.environment)
        self.assertEqual(bm.last_stderr, '')
        self.assertEqual(bm.last_stdout, '')
        self.assertEqual(retval, 0)

    def test_simple_run(self):
        """Examine examples/upstream1 as used in driver tests. Should have
           a single run with a single cell.
        """
        bm = self.bm
        self.environment['UPSTREAM_LOC'] = EXAMPLES + '/upstream1'
        self.environment['UPSTREAM_NAME'] = 'TEST'

        retval = bm.runscript(SCRIPT, env=self.environment)

        self.assertEqual(retval, 0)
        self.assertEqual(bm.last_stderr, '')
        self.assertEqual(bm.last_stdout.split('\t'), [ '20190226_TEST_testrun',
                                                       EXAMPLES + '/upstream1/testrun',
                                                       'testlib/20190226_1723_2-A5-D5_PAD38578_c6ded78b\n' ])

    def test_silly_run_name(self):
        """If there is a space in the run name it should be sanitized. Not sure if it's
           possible to put funny characters in a Library/Pool name, but we should really avoid that.
        """
        bm = self.bm
        self.environment['UPSTREAM_LOC'] = EXAMPLES + '/upstream_silly_names'
        self.environment['UPSTREAM_NAME'] = 'TEST'

        retval = bm.runscript(SCRIPT, env=self.environment)

        self.assertEqual(retval, 0)
        self.assertEqual(bm.last_stderr, '')
        self.assertEqual(bm.last_stdout.split('\t'), [ '20190226_TEST_name_with_spaces',
                                                       EXAMPLES + '/upstream_silly_names/name  with___spaces',
                                                       'testlib/20190226_1723_2-A5-D5_PAD38578_c6ded78b\n' ])


    def test_ssh(self):
        """With a ':' in the UPSTREAM_LOC, ssh should be invoked
        """
        bm = self.bm
        self.environment['UPSTREAM_LOC'] = 'foo@bar.example.com:whatever'
        self.environment['UPSTREAM_NAME'] = 'TEST'

        retval = bm.runscript(SCRIPT, env=self.environment)

        self.assertEqual(retval, 0)
        self.assertEqual(bm.last_stderr, '')
        self.assertEqual(bm.last_stdout, '')

        self.assertEqual(len(bm.last_calls['ssh']), 1)
        self.assertEqual( bm.last_calls['ssh'][0][:7],
                          ["-o", "ConnectTimeout=5", "-T", "foo@bar.example.com", "cd", "whatever", "&&"] )

if __name__ == '__main__':
    unittest.main()
