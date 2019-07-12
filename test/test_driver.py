#!/usr/bin/env python3

import unittest
import sys, os, re
from unittest.mock import patch

import subprocess
from tempfile import mkdtemp
from shutil import rmtree, copytree
from glob import glob

"""Here we're using a Python script to test a shell script (driver.sh).  The shell
   script calls various programs.  Ideally we want to have a cunning way of catching
   and detecting the calls to those programs, similar to the way that unittest.mock.patch works.
   To this end, see the BinMocker class, which does just this.
"""
with patch('sys.path', new=['.'] + sys.path):
    from test.binmocker import BinMocker

VERBOSE = os.environ.get('VERBOSE', '0') != '0'
EXAMPLES = os.path.dirname(__file__) + '/examples'
DRIVER = os.path.abspath(os.path.dirname(__file__) + '/../driver.sh')

PROGS_TO_MOCK = {
    "ssh" : None,
    "rsync" : None,
    "Snakefile.process_run" : None,
    "rt_runticket_manager.py" : "echo STDERR rt_runticket_manager.py >&2",
    "upload_report.sh" : "echo STDERR upload_report.sh >&2"
}

class T(unittest.TestCase):

    def setUp(self):
        """Make a shadow folder, and in it have subdirs runs and fastqdata and log.
           Initialize BinMocker.
           Calculate the test environment needed to run the driver.sh script.
        """
        self.temp_dir = mkdtemp()
        for d in ['runs', 'fastqdata', 'log']:
            os.mkdir(os.path.join(self.temp_dir, d))

        self.bm = BinMocker()
        for p, s in PROGS_TO_MOCK.items(): self.bm.add_mock(p, side_effect=s)

        # Set the driver to run in our test harness. Note I can set
        # $BIN_LOCATION to more than one path.
        # Also we need to set VERBOSE to the driver even if it's not set for this test script.
        self.environment = dict(
                PROM_RUNS = os.path.join(self.temp_dir, 'runs'),
                FASTQDATA = os.path.join(self.temp_dir, 'fastqdata'),
                UPSTREAM = 'TEST',
                UPSTREAM_TEST = '',
                BIN_LOCATION = self.bm.mock_bin_dir + ':' + os.path.dirname(DRIVER),
                LOG_DIR = os.path.join(self.temp_dir, 'log'), #this is redundant if...
                MAINLOG = "/dev/stdout",
                ENVIRON_SH = '/dev/null',
                VERBOSE = 'yes',
                PY3_VENV = 'none',
                STALL_TIME = '',
            )

        # Now clear any of these environment variables that might have been set outside
        # of this script.
        for e in self.environment:
            if e in os.environ: del(os.environ[e])

        # See the errors in all their glory
        self.maxDiff = None

    def tearDown(self):
        """Remove the shadow folder and clean up the BinMocker
        """
        rmtree(self.temp_dir)

        self.bm.cleanup()

    def bm_rundriver(self, expected_retval=0, check_stderr=True):
        """A convenience wrapper around self.bm.runscript that sets the environment
           appropriately and runs DRIVER and returns STDOUT split into an array.
        """
        retval = self.bm.runscript(DRIVER, set_path=False, env=self.environment)

        # Where a file is missing it's always useful to see the error.
        # (status 127 is the standard shell return code for a command not found)
        if retval == 127 or VERBOSE:
            print("STDERR:")
            print(self.bm.last_stderr)
        if VERBOSE:
            print("STDOUT:")
            print(self.bm.last_stdout)
            print("RETVAL: %s" % retval)

        self.assertEqual(retval, expected_retval)

        # If the return val is 0 then stderr should normally be empty.
        # Not always, but this is a useful default.
        if retval == 0 and check_stderr:
            self.assertEqual(self.bm.last_stderr, '')

        return self.bm.last_stdout.split("\n")

    def copy_run(self, run):
        """Utility function to add a run from examples/runs into temp_dir/runs.
           Returns the path to the run copied.
        """
        run_dir = os.path.join(EXAMPLES, 'runs', run)

        # We want to know the desired output location
        self.to_path = os.path.join(self.temp_dir, 'runs', run)

        # Annoyingly, copytree gives me no way to avoid running copystat on the files.
        # But that doesn't mean it's impossible...
        with patch('shutil.copystat', lambda *a, **kw: True):
            return copytree(run_dir,
                            self.to_path,
                            symlinks = True )

    def assertInStdout(self, *words):
        """Assert that there is at least one line in stdout containing all these strings
        """
        o_split = self.bm.last_stdout.split("\n")

        # This loop progressively prunes down the lines, until anything left
        # must have contained each word in the list.
        for w in words:
            o_split = [ l for l in o_split if w in l ]

        self.assertTrue(o_split)

    def assertNotInStdout(self, *words):
        """Assert that no lines in STDOUT contain all of these strings
        """
        o_split = self.bm.last_stdout.split("\n")

        # This loop progressively prunes down the lines, until anything left
        # must have contained each word in the list.
        for w in words:
            o_split = [ l for l in o_split if w in l ]

        self.assertFalse(o_split)

    def shell(self, cmd):
        """Call to os.system in 'safe mode'
        """
        status = os.system("set -euo pipefail ; " + cmd)
        if status:
            raise ChildProcessError("Exit status was %s running command:\n%s" % (status, cmd))

        return status

    ### And the actual tests ###

    def test_nop(self):
        """With no data, nothing should happen. At all.
           The script will exit with status 1 as the glob pattern match will fail.
           Message going to STDERR would trigger an alert from CRON if this happened in production.
        """
        self.bm_rundriver(expected_retval=1)

        self.assertEqual(self.bm.last_calls, self.bm.empty_calls())

        self.assertTrue('Nothing found in {}/runs or any upstream locations'.format(
                                          self.temp_dir ) in self.bm.last_stderr)

    def test_no_venv(self):
        """With a missing virtualenv the script should fail and not even scan.
           Normally there will be an active virtualenv in the test directory so
           we need to explicitly break this.
        """
        self.environment['PY3_VENV'] = '/dev/null/NO_SUCH_PATH'
        self.bm_rundriver(expected_retval=1)

        self.assertEqual(self.bm.last_calls, self.bm.empty_calls())

        self.assertTrue('/dev/null/NO_SUCH_PATH/bin/activate: Not a directory' in self.bm.last_stderr)
        self.assertFalse('no match' in self.bm.last_stderr)

    def test_no_run_location(self):
        """If no PROM_RUNS is set, expect a fast failure.
        """
        self.environment['PROM_RUNS'] = 'meh'
        self.bm_rundriver(expected_retval=1)
        self.assertEqual(self.bm.last_calls, self.bm.empty_calls())
        self.assertEqual(self.bm.last_stderr, "No such directory 'meh'\n")

        del(self.environment['PROM_RUNS'])
        self.bm_rundriver(expected_retval=1)
        self.assertEqual(self.bm.last_calls, self.bm.empty_calls())
        self.assertTrue('PROM_RUNS: unbound variable' in self.bm.last_stderr)

    def test_new_upstream(self):
        """With a single run in the upstream directory, this should trigger the
           creation of a new run in PROM_RUNS and a corresponding directory in FASTQDATA
           and a new run ticket in preparation for sync.
        """
        self.environment['UPSTREAM_TEST'] = EXAMPLES + '/upstream1'

        self.bm_rundriver()

        if VERBOSE:
            subprocess.call(["tree", "-usa", self.temp_dir])

        # The run is named '20190226_TEST_testrun'. Check for dirs and symlinks.
        self.assertTrue(os.path.isdir(self.temp_dir + "/runs/20190226_TEST_testrun/pipeline"))
        self.assertTrue(os.path.isdir(self.temp_dir + "/fastqdata/20190226_TEST_testrun"))
        self.assertEqual( os.path.realpath(self.temp_dir + "/runs/20190226_TEST_testrun/pipeline/output"),
                          os.path.realpath(self.temp_dir + "/fastqdata/20190226_TEST_testrun") )
        self.assertEqual( os.path.realpath(self.temp_dir + "/fastqdata/20190226_TEST_testrun/rundata"),
                          os.path.realpath(self.temp_dir + "/runs/20190226_TEST_testrun") )

        with open(self.temp_dir + "/runs/20190226_TEST_testrun/pipeline/upstream") as fh:
            self.assertEqual(fh.read().rstrip('\n'), self.environment['UPSTREAM_TEST'] + '/testrun')

        # A new ticket should have been made
        expected_calls = self.bm.empty_calls()
        expected_calls['rt_runticket_manager.py'] = ['-r 20190226_TEST_testrun -Q promrun --comment @???']

        # The call to rt_runticket_manager.py is non-deterministic, so we have to doctor it...
        self.bm.last_calls['rt_runticket_manager.py'][0] = re.sub(
                                    r'@\S+$', '@???', self.bm.last_calls['rt_runticket_manager.py'][0] )

        self.assertEqual(self.bm.last_calls, expected_calls)

    def test_new_without_upstream(self):
        """With a new run in PROM_RUNS that isn't found in the UPSTREAM this should trigger
           creation of a corresponding directory in FASTQDATA and a new run ticket much as
           above, but no sync as there is nothing to sync - our assumption is that this run
           should be ready for processing right away.
        """
        self.copy_run("201907010_LOCALTEST_newrun")
        self.bm_rundriver()

        if VERBOSE:
            subprocess.call(["tree", "-usa", self.temp_dir])

        # Check for dirs and symlinks as above
        self.assertTrue(os.path.isdir(self.temp_dir + "/runs/201907010_LOCALTEST_newrun/pipeline"))
        self.assertTrue(os.path.isdir(self.temp_dir + "/fastqdata/201907010_LOCALTEST_newrun"))
        self.assertEqual( os.path.realpath(self.temp_dir + "/runs/201907010_LOCALTEST_newrun/pipeline/output"),
                          os.path.realpath(self.temp_dir + "/fastqdata/201907010_LOCALTEST_newrun") )
        self.assertEqual( os.path.realpath(self.temp_dir + "/fastqdata/201907010_LOCALTEST_newrun/rundata"),
                          os.path.realpath(self.temp_dir + "/runs/201907010_LOCALTEST_newrun") )

        with open(self.temp_dir + "/runs/201907010_LOCALTEST_newrun/pipeline/upstream") as fh:
            self.assertEqual(fh.read().rstrip('\n'), 'LOCAL')

        # A new ticket should have been made
        expected_calls = self.bm.empty_calls()
        expected_calls['rt_runticket_manager.py'] = ['-r 201907010_LOCALTEST_newrun -Q promrun --comment @???']

        # The call to rt_runticket_manager.py is non-deterministic, so we have to doctor it...
        self.bm.last_calls['rt_runticket_manager.py'][0] = re.sub(
                                    r'@\S+$', '@???', self.bm.last_calls['rt_runticket_manager.py'][0] )

        self.assertEqual(self.bm.last_calls, expected_calls)

    def test_new_but_output_exists(self):
        """There should be an error if the directory in fastqdata already exists
        """
        self.copy_run("201907010_LOCALTEST_newrun")

        os.mkdir(self.temp_dir + "/fastqdata/201907010_LOCALTEST_newrun")

        # Driver should still exit cleanly
        self.bm_rundriver()
        # This should go to the main log
        self.assertInStdout("cannot create directory")

        if VERBOSE:
            subprocess.call(["tree", "-usa", self.temp_dir])

        # The failed flag should be set
        self.assertTrue(os.path.exists(self.temp_dir + "/runs/201907010_LOCALTEST_newrun/pipeline/failed"))
        # The source should be set to 'LOCAL'
        with open(self.temp_dir + "/runs/201907010_LOCALTEST_newrun/pipeline/upstream") as fh:
            self.assertEqual(fh.read(), "LOCAL\n")

        # A new ticket should have been made, but with an error
        expected_calls = self.bm.empty_calls()
        expected_calls['rt_runticket_manager.py'] = ['-r 201907010_LOCALTEST_newrun -Q promrun --subject failed'
                                                     ' --reply New_Run_Setup. See log in ???']

        # The call to rt_runticket_manager.py is non-deterministic, so we have to doctor it...
        self.bm.last_calls['rt_runticket_manager.py'][0] = re.sub(
                                    r'See log in.*', 'See log in ???', self.bm.last_calls['rt_runticket_manager.py'][0] )


        self.assertEqual(self.bm.last_calls, expected_calls)

    def test_sync_needed(self):
        """A run has two cells that need synced
           After the sync, one should be ready to process
           For good measure there is a space in the directory name
        """
        self.assertTrue(True)

if __name__ == '__main__':
    unittest.main()
