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
    "chgrp": None,
    "ssh" : None,
    "rsync" : None,
    "Snakefile.main" : None,
    "rt_runticket_manager.py" : "echo STDERR rt_runticket_manager.py >&2",
    "upload_report.sh" : "echo STDERR upload_report.sh >&2",
    "del_remote_cells.sh" : "echo STDERR del_remote_cells.sh >&2"
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
                DEL_REMOTE_CELLS = 'yes',
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

    def copy_run(self, run, subdir=None):
        """Utility function to add a run from examples/runs into temp_dir/runs.
           Returns the path to the run copied.
        """
        run_dir = os.path.join(EXAMPLES, 'runs', run)

        # We want to know the desired output location
        # Note if you copy multiple runs then self.run_path will just be the last
        if subdir:
            os.mkdir(os.path.join(self.temp_dir, 'runs', subdir))
            self.run_path = os.path.join(self.temp_dir, 'runs', subdir, run)
        else:
            self.run_path = os.path.join(self.temp_dir, 'runs', run)

        # Annoyingly, copytree gives me no way to avoid running copystat on the files.
        # But that doesn't mean it's impossible...
        with patch('shutil.copystat', lambda *a, **kw: True):
            return copytree(run_dir,
                            self.run_path,
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

    def assertInStderr(self, *words):
        """Assert that there is at least one line in stdout containing all these strings
        """
        o_split = self.bm.last_stderr.split("\n")

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

    def touch(self, fp, content="meh"):
        """Create a new file within self.run_path
        """
        with open(os.path.join(self.run_path, fp), 'w') as fh:
            print(content, file=fh)

    ### And the actual tests ###

    def test_nop(self):
        """With no data, nothing should happen. At all.
           The script will exit with status 1 as the glob pattern match will fail.
           Message going to STDERR would trigger an alert from CRON if this happened in production.
        """
        self.bm_rundriver(expected_retval=1)

        self.assertEqual(self.bm.last_calls, self.bm.empty_calls())

        self.assertInStdout("Found 0 cells in upstream runs")
        self.assertInStderr('Nothing found matching {}/runs/.*_.* or in any upstream locations'.format(self.temp_dir))

    def test_nop_withbatch(self):
        """Check that setting PROM_RUNS_BATCH does the same as above, with a slightly
           different error.
        """
        self.environment['PROM_RUNS_BATCH'] = 'month'
        self.bm_rundriver(expected_retval=1)

        self.assertEqual(self.bm.last_calls, self.bm.empty_calls())

        self.assertInStdout("Found 0 cells in upstream runs")
        self.assertInStderr(r'Nothing found matching ' + self.temp_dir + '/runs/\d{4}-\d{2}/.*_.* or in any upstream locations')

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
            self.assertEqual(fh.read(), self.environment['UPSTREAM_TEST'] + '/testrun\n')

        # A new ticket should have been made
        expected_calls = self.bm.empty_calls()
        expected_calls['chgrp'] = [['-c', '--reference='+self.temp_dir+"/fastqdata/20190226_TEST_testrun", './pipeline']]
        expected_calls['rt_runticket_manager.py'] = ['-r 20190226_TEST_testrun -Q promrun --subject new --comment @???'.split()]

        # The call to rt_runticket_manager.py is non-deterministic, so we have to doctor it...
        self.bm.last_calls['rt_runticket_manager.py'][0][-1] = re.sub(
                                    r'@\S+$', '@???', self.bm.last_calls['rt_runticket_manager.py'][0][-1] )

        self.assertEqual(self.bm.last_calls, expected_calls)

        # The STDERR from upload_report.sh and rt_runticket_manager.py should end
        # up in the per-run log.
        log_lines = slurp_file(self.temp_dir + "/fastqdata/20190226_TEST_testrun/pipeline.log")
        self.assertTrue('STDERR rt_runticket_manager.py') in log_lines
        self.assertTrue('STDERR upload_report.sh') in log_lines
        self.assertTrue('cat: pipeline/report_upload_url.txt: No such file or directory') in log_lines

    def test_new_upstream_withbatch(self):
        """Check that setting PROM_RUNS_BATCH works.
        """
        self.environment['PROM_RUNS_BATCH'] = 'month'
        self.environment['UPSTREAM_TEST'] = EXAMPLES + '/upstream1'

        self.bm_rundriver()

        if VERBOSE:
            subprocess.call(["tree", "-usa", self.temp_dir])

        # The run is named '20190226_TEST_testrun'. Check for dirs and symlinks.
        self.assertTrue(os.path.isdir(self.temp_dir + "/runs/2019-02/20190226_TEST_testrun/pipeline"))
        self.assertTrue(os.path.isdir(self.temp_dir + "/fastqdata/20190226_TEST_testrun"))
        self.assertEqual( os.path.realpath(self.temp_dir + "/runs/2019-02/20190226_TEST_testrun/pipeline/output"),
                          os.path.realpath(self.temp_dir + "/fastqdata/20190226_TEST_testrun") )
        self.assertEqual( os.path.realpath(self.temp_dir + "/fastqdata/20190226_TEST_testrun/rundata"),
                          os.path.realpath(self.temp_dir + "/runs/2019-02/20190226_TEST_testrun") )


    def test_new_upstream2(self):
        """A slightly more complex run with spaces in the lib name.
           Note that the spaces may well break downstream parts.
        """
        self.environment['UPSTREAM_TEST'] = EXAMPLES + '/upstream2'
        self.bm_rundriver()

        if VERBOSE:
            subprocess.call(["tree", "-usa", self.temp_dir])

        self.assertTrue(os.path.isdir(self.temp_dir + "/runs/20000101_TEST_testrun2/pipeline"))

        # Did we correctly see the three cells?
        self.assertInStdout("NEW 20000101_TEST_testrun2 with 3 cells")

        # Is the upstream written correctly?
        with open(self.temp_dir + "/runs/20000101_TEST_testrun2/pipeline/upstream") as fh:
            self.assertEqual(fh.read(), self.environment['UPSTREAM_TEST'] + '/testrun2\n')

    def test_new_upstream2_withbatch(self):
        """Same with PROM_RUNS_BATCH=year
        """
        self.environment['PROM_RUNS_BATCH'] = 'year'
        self.environment['UPSTREAM_TEST'] = EXAMPLES + '/upstream2'
        self.bm_rundriver()

        if VERBOSE:
            subprocess.call(["tree", "-usa", self.temp_dir])

        self.assertTrue(os.path.isdir(self.temp_dir + "/runs/2000/20000101_TEST_testrun2/pipeline"))

        # Did we correctly see the three cells?
        self.assertInStdout("NEW 20000101_TEST_testrun2 with 3 cells")
        self.assertInStdout(self.environment['UPSTREAM_TEST'])
        self.assertInStdout(self.temp_dir + "/runs/2000/20000101_TEST_testrun2")

        # Is the upstream written correctly?
        with open(self.temp_dir + "/runs/2000/20000101_TEST_testrun2/pipeline/upstream") as fh:
            self.assertEqual(fh.read(), self.environment['UPSTREAM_TEST'] + '/testrun2\n')

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
        expected_calls['chgrp'] = [['-c', '--reference='+self.temp_dir+"/fastqdata/201907010_LOCALTEST_newrun", './pipeline']]
        expected_calls['rt_runticket_manager.py'] = ['-r 201907010_LOCALTEST_newrun -Q promrun --subject new --comment @???'.split()]

        # The call to rt_runticket_manager.py is non-deterministic, so we have to doctor it...
        self.bm.last_calls['rt_runticket_manager.py'][0][-1] = re.sub(
                                    r'@\S+$', '@???', self.bm.last_calls['rt_runticket_manager.py'][0][-1] )

        self.assertEqual(self.bm.last_calls, expected_calls)

    def test_empty_upstream(self):
        """With nothing to process and no upstream, we should also fail. However the error coming from
           list_remote_cells.sh shouldn't leak to STDERR as was happening in 0.6.0.
        """
        # Make a run but it's aborted so we'll ignore it.
        self.copy_run("20000101_TEST_testrun2")
        self.touch("pipeline/aborted")

        # An empty upstream location
        self.environment['UPSTREAM_TEST'] = EXAMPLES + '/empty'

        # This should be OK
        self.bm_rundriver(expected_retval=0)

        self.assertEqual(self.bm.last_calls, self.bm.empty_calls())

        self.assertInStdout("Found 0 cells in upstream runs")
        self.assertInStdout("ls: cannot access '*/*/20??????_*_????????/fast?_????': No such file or directory")

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
        expected_calls['rt_runticket_manager.py'] = [['-r', '201907010_LOCALTEST_newrun', '-Q', 'promrun', '--subject', 'failed',
                                                      '--reply', 'Failed at New_Run_Setup.\nSee log in /dev/stdout']]

        # And nothing should be written to the fastqdata dir
        self.assertEqual(os.listdir(self.temp_dir + "/fastqdata/201907010_LOCALTEST_newrun"), [])

        self.assertEqual(self.bm.last_calls, expected_calls)

    def test_sync_needed(self):
        """A run has two cells that need synced and one completely new one.
           After the sync, we'll force one to be ready to process
           For good measure there is a space in the directory name.
        """
        # Note the upstream2 example is also used by test_run_status.py so check all is well
        # with those before trying to diagnose faults here.
        self.environment['UPSTREAM_TEST'] = EXAMPLES + '/upstream2'
        self.environment['SYNC_CMD'] = 'rsync =$upstream_host= =$upstream_path= =$run= =$cell='
        self.copy_run('20000101_TEST_testrun2')

        #self.touch("a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa/final_summary.txt")
        self.touch("a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa/final_summary_PAD00000_1ea085ce.txt")

        self.bm_rundriver()

        self.assertInStdout("SYNC_NEEDED 20000101_TEST_testrun2")
        # Because of final_summary.txt we should see this:
        self.assertTrue(os.path.exists(self.run_path + "/pipeline/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa.synced"))

        expected_calls = self.bm.empty_calls()
        rsync_first_bit = ["==", "={}=".format(EXAMPLES + '/upstream2/testrun2'), "=20000101_TEST_testrun2="]
        expected_calls['rsync'] = [ rsync_first_bit + ["=a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa="],
                                    rsync_first_bit + ["=a test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb="],
                                    rsync_first_bit + ["=another test/20000101_0000_3-C1-C1_PAD00000_cccccccc="] ]
        self.assertEqual(self.bm.last_calls, expected_calls)

    def test_sync_needed_withbatch(self):
        """Same with PROM_RUNS_BATCH=year
        """
        self.environment['PROM_RUNS_BATCH'] = 'year'
        self.environment['UPSTREAM_TEST'] = EXAMPLES + '/upstream2'
        self.environment['SYNC_CMD'] = 'rsync =$upstream_host= =$upstream_path= =$run= =$cell='
        self.copy_run('20000101_TEST_testrun2', subdir="2000")

        #self.touch("a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa/final_summary.txt")
        self.touch("a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa/final_summary_PAD00000_1ea085ce.txt")

        self.bm_rundriver()

        self.assertInStdout("SYNC_NEEDED 20000101_TEST_testrun2")
        # Because of final_summary.txt we should see this:
        self.assertTrue(os.path.exists(self.run_path + "/pipeline/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa.synced"))

        expected_calls = self.bm.empty_calls()
        rsync_first_bit = ["==", "={}=".format(EXAMPLES + '/upstream2/testrun2'), "=20000101_TEST_testrun2="]
        expected_calls['rsync'] = [ rsync_first_bit + ["=a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa="],
                                    rsync_first_bit + ["=a test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb="],
                                    rsync_first_bit + ["=another test/20000101_0000_3-C1-C1_PAD00000_cccccccc="] ]
        self.assertEqual(self.bm.last_calls, expected_calls)

    def test_run_complete(self):
        """Same run as above, but skip past the syncing part.
           When the pipeline runs again it should notify the run as complete and kick off
           processing and do all the other stuff.
        """
        self.copy_run('20000101_TEST_testrun2')
        self.touch("pipeline/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa.synced")
        self.touch("pipeline/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb.synced")

        self.bm_rundriver()
        self.assertInStdout("CELL_READY 20000101_TEST_testrun2")
        self.assertTrue(os.path.exists(self.run_path + "/pipeline/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa.done"))
        self.assertTrue(os.path.exists(self.run_path + "/pipeline/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb.done"))
        self.assertFalse(os.path.exists(self.run_path + "/pipeline/failed"))

        # Doctor non-deterministic calls to rt_runticket_manager.py
        for i, c in enumerate(self.bm.last_calls['rt_runticket_manager.py']):
            self.bm.last_calls['rt_runticket_manager.py'][i][-1] = re.sub( r'@\S+$', '@???', c[-1] )

        expected_calls = self.bm.empty_calls()
        expected_calls['Snakefile.main'] = [[ "-f", "--config",
                                              "cellsready=a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa\t"
                                                         "a test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb",
                                              "cells=a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa\t"
                                                    "a test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb",
                                              "-R", "per_cell_blob_plots", "per_project_blob_tables", "one_cell", "nanostats",
                                              "--", "pack_fast5", "main" ]]
        expected_calls['upload_report.sh'] = [[ self.run_path + "/pipeline/output" ]]
        expected_calls['rt_runticket_manager.py'] = [[ "-r", "20000101_TEST_testrun2", "-Q", "promrun", "--subject", "processing",
                                                       "--reply",
                                                       "All 2 cells have run on the instrument. Full report will follow soon."],
                                                     [ "-r", "20000101_TEST_testrun2", "-Q", "promrun", "--subject", "processing",
                                                       "--comment", "@???"],
                                                     [ "-r", "20000101_TEST_testrun2", "-Q", "promrun", "--subject", "Finished pipeline",
                                                       "--reply", "@???" ]]
        expected_calls['del_remote_cells.sh'] = [[ "/DUMMY/PATH/20000101_TEST_testrun2",
                                                   "a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa",
                                                   "a test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb" ]]

        self.assertEqual(self.bm.last_calls, expected_calls)

    def test_run_partial(self):
        """Same run as above, but only one cell is ready.
           When the pipeline runs again it should NOT notify the run as complete but the one cell
           should be processed (higher priority than starting the sync).
        """
        self.copy_run('20000101_TEST_testrun2')
        self.touch("pipeline/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa.synced")

        self.bm_rundriver()
        self.assertInStdout("CELL_READY 20000101_TEST_testrun2")

        # Doctor non-deterministic calls to rt_runticket_manager.py
        for i, c in enumerate(self.bm.last_calls['rt_runticket_manager.py']):
            self.bm.last_calls['rt_runticket_manager.py'][i][-1] = re.sub( r'@\S+$', '@???', c[-1] )

        expected_calls = self.bm.empty_calls()
        expected_calls['Snakefile.main'] = [[ "-f", "--config",
                                              "cellsready=a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa",
                                              "cells=a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa\t"
                                                    "a test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb",
                                              "-R", "per_cell_blob_plots", "per_project_blob_tables", "one_cell", "nanostats",
                                              "--", "pack_fast5", "main" ]]
        expected_calls['upload_report.sh'] = [[ self.run_path + "/pipeline/output" ]]
        expected_calls['rt_runticket_manager.py'] = ["-r 20000101_TEST_testrun2 -Q promrun --subject processing --comment @???".split(),
                                                     "-r 20000101_TEST_testrun2 -Q promrun --subject incomplete --comment @???".split()]
        expected_calls['del_remote_cells.sh'] = [[ "/DUMMY/PATH/20000101_TEST_testrun2", "a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa" ]]

        self.assertEqual(self.bm.last_calls, expected_calls)

    def test_run_complete_rtfail(self):
        """Same as test_run_complete, but messaging to RT fails.
           The run should press on up to the final stage but should then fail and
           not del_remote_cells
        """
        self.copy_run('20000101_TEST_testrun2')
        self.touch("pipeline/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa.synced")
        self.touch("pipeline/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb.synced")

        # When the driver can't report a failure to RT, it will log an error to STDERR so that
        # the CRON can send us warning messages directly.
        self.bm.add_mock('rt_runticket_manager.py', fail=True)
        self.bm_rundriver(check_stderr=False)

        self.assertInStdout("CELL_READY 20000101_TEST_testrun2")
        self.assertInStdout("Failed to send summary to RT.")
        self.assertInStderr("FAIL Reporting for cells")
        self.assertInStderr("and also failed to report the error via RT")

        self.assertFalse(os.path.exists(self.run_path + "/pipeline/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa.done"))
        self.assertFalse(os.path.exists(self.run_path + "/pipeline/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb.done"))
        self.assertTrue(os.path.exists(self.run_path + "/pipeline/failed"))

        # Doctor non-deterministic calls to rt_runticket_manager.py
        rtcalls = self.bm.last_calls['rt_runticket_manager.py']
        for i in range(len(rtcalls)):
            rtcalls[i][-1] = re.sub( r'@\S+$', '@???', rtcalls[i][-1] )

        expected_calls = self.bm.empty_calls()
        expected_calls['Snakefile.main'] = [[ "-f", "--config",
                                              "cellsready=a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa\t"
                                                         "a test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb",
                                              "cells=a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa\t"
                                                    "a test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb",
                                              "-R", "per_cell_blob_plots", "per_project_blob_tables", "one_cell", "nanostats",
                                              "--", "pack_fast5", "main" ]]
        expected_calls['upload_report.sh'] = [[ self.run_path + "/pipeline/output" ]]
        expected_calls['rt_runticket_manager.py'] = [[ "-r", "20000101_TEST_testrun2", "-Q", "promrun", "--subject", "processing",
                                                       "--reply",
                                                       "All 2 cells have run on the instrument. Full report will follow soon." ],
                                                     [ "-r", "20000101_TEST_testrun2", "-Q", "promrun", "--subject", "processing",
                                                       "--comment", "@???"],
                                                     [ "-r", "20000101_TEST_testrun2", "-Q", "promrun", "--subject", "Finished pipeline",
                                                       "--reply", "@???"],
                                                     [ "-r", "20000101_TEST_testrun2", "-Q", "promrun", "--subject", "failed",
                                                       "--reply",
                                                       "Failed at Reporting for cells [\n"
                                                       "\ta test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa,\n"
                                                       "\ta test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb\n"
                                                       "].\n"
                                                       "See log in " + self.run_path + "/pipeline/output/pipeline.log" ]]
        expected_calls['del_remote_cells.sh'] = []

        self.assertEqual(self.bm.last_calls, expected_calls)

    def test_run_partial_rtfail(self):
        """What if RT communication fails on a partial run?
           Well I shouldn't enter fail state as I want to keep processing cells if poss.
           But also I don't want the cell to be deleted or marked done until RT is notified.
           Maybe I need to only do deletions when the run is fully processed??
           For now I'll just need to enter failed state. Anything else would need a change
           to the state machine.
        """
        self.copy_run('20000101_TEST_testrun2')
        self.touch("pipeline/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa.synced")

        # When the driver can't report a failure to RT, it will log an error to STDERR so that
        # the CRON can send us warning messages directly.
        self.bm.add_mock('rt_runticket_manager.py', fail=True)
        self.bm_rundriver(check_stderr=False)

        self.assertInStdout("CELL_READY 20000101_TEST_testrun2")
        self.assertInStdout("Failed to send summary to RT.")
        self.assertInStderr("FAIL Reporting for cells")
        self.assertInStderr("and also failed to report the error via RT")

        self.assertFalse(os.path.exists(self.run_path + "/pipeline/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa.done"))
        self.assertFalse(os.path.exists(self.run_path + "/pipeline/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb.done"))
        self.assertTrue(os.path.exists(self.run_path + "/pipeline/failed"))

        # Doctor non-deterministic calls to rt_runticket_manager.py
        rtcalls = self.bm.last_calls['rt_runticket_manager.py']
        for i in range(len(rtcalls)):
            rtcalls[i][-1] = re.sub( r'@\S+$', '@???', rtcalls[i][-1] )

        expected_calls = self.bm.empty_calls()
        expected_calls['Snakefile.main'] = [[ "-f", "--config",
                                              "cellsready=a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa",
                                              "cells=a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa\t"
                                                    "a test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb",
                                              "-R", "per_cell_blob_plots", "per_project_blob_tables", "one_cell", "nanostats",
                                              "--", "pack_fast5", "main" ]]
        expected_calls['upload_report.sh'] = [[ self.run_path + "/pipeline/output" ]]
        expected_calls['rt_runticket_manager.py'] = [ "-r 20000101_TEST_testrun2 -Q promrun --subject processing --comment @???".split(),
                                                      "-r 20000101_TEST_testrun2 -Q promrun --subject incomplete --comment @???".split(),
                                                      [ "-r", "20000101_TEST_testrun2", "-Q", "promrun", "--subject", "failed",
                                                        "--reply",
                                                        "Failed at Reporting for cells [\n"
                                                        "\ta test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa\n"
                                                        "].\n"
                                                        "See log in " + self.run_path + "/pipeline/output/pipeline.log" ]]
        expected_calls['del_remote_cells.sh'] = []

        self.assertEqual(self.bm.last_calls, expected_calls)

def slurp_file(f):
    with open(f) as fh:
        return [ l.rstrip('\n') for l in fh ]

if __name__ == '__main__':
    unittest.main()
