#!/usr/bin/env python3

"""Base class for other tests that check the behaviour of driver.sh

   driver.sh has very complex behaviour and weird error handling to my
   approach is to test it to death.
"""

import unittest
import sys, os, re
from unittest.mock import patch
import yaml, yamlloader

from tempfile import mkdtemp
from shutil import rmtree, copytree

"""Here we're using a Python script to test a shell script (driver.sh).  The shell
   script calls various programs.  Ideally we want to have a cunning way of catching
   and detecting the calls to those programs, similar to the way that unittest.mock.patch works.
   To this end, see the BashMocker class, which does just this.
"""
from bashmocker import BashMocker

VERBOSE = os.environ.get('VERBOSE', '0') != '0'
EXAMPLES = os.path.dirname(__file__) + '/examples'
DRIVER = os.path.abspath(os.path.dirname(__file__) + '/../driver.sh')

PROGS_TO_MOCK = {
    "chgrp": None,
    "ssh" : None,
    "rsync" : None,
    "Snakefile.main" : None,
    "rt_runticket_manager.py" : "echo STDERR rt_runticket_manager.py >&2",
    "upload_report.sh" : "echo STDERR upload_report.sh >&2 ; echo http://dummylink",
    "del_remote_cells.sh" : "echo STDERR del_remote_cells.sh >&2",
    "scan_cells.py" : None,
}

# Snakemake targets are always the same, unless $MAIN_SNAKE_TARGETS is set
SNAKE_TARGETS = ("copy_fast5 main -f"
                 " -R per_cell_blob_plots per_project_blob_tables one_cell"
                 "    nanostats convert_final_summary sample_names"
                 " --config".split())


class TestDriverBase(unittest.TestCase):

    def __init__(self, *args):
        super().__init__(*args)
        self.verbose = VERBOSE
        self.snake_targets = SNAKE_TARGETS
        self.examples = EXAMPLES
        self.example_runs = os.path.join(self.examples, "runs")
        self.progs_to_mock = PROGS_TO_MOCK

    def setUp(self):
        """Make a shadow folder, and in it have subdirs runs and fastqdata and log.
           Initialize BashMocker.
           Calculate the test environment needed to run the driver.sh script.
        """
        self.temp_dir = mkdtemp()
        for d in ['runs', 'fastqdata', 'log']:
            os.mkdir(os.path.join(self.temp_dir, d))

        self.bm = BashMocker()
        for p, s in self.progs_to_mock.items(): self.bm.add_mock(p, side_effect=s)

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
                TOOLBOX = '/dev/null'
            )

        # Now clear any of these environment variables that might have been set outside
        # of this script.
        for e in self.environment:
            if e in os.environ: del(os.environ[e])

        # See the errors in all their glory
        self.maxDiff = None

        self.run_name = None

    def tearDown(self):
        """Remove the shadow folder and clean up the BashMocker
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
        self.run_name = run
        run_dir = os.path.join(self.example_runs, run)

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

    def rt_cmd(self, *args):
        """Get the expected args to rt_runticket_manager.py
        """
        return [*f"-r {self.run_name} -Q promrun_internal -P Experiment --subject".split(), *args]

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

    # Most of the actual tests are in the base classes
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


def slurp_file(f):
    with open(f) as fh:
        return [ l.rstrip('\n') for l in fh ]

def load_yaml(yaml_file):
    with open(yaml_file) as yfh:
        return yaml.load(yfh, Loader=yamlloader.ordereddict.CSafeLoader)
