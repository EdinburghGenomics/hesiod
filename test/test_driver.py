#!/usr/bin/env python3

import unittest
import sys, os, re
from unittest.mock import patch

import subprocess
from tempfile import mkdtemp
from shutil import rmtree, copytree
from glob import glob

from test_driver_base import slurp_file, TestDriverBase, load_yaml

EXAMPLES = os.path.dirname(__file__) + '/examples'

class T(TestDriverBase):

    # See TestDriverBase for all the utility stuff
    def __init__(self, *args):
        super().__init__(*args)
        self.examples = EXAMPLES

    def test_new_upstream(self):
        """With a single run in the upstream directory, this should trigger the
           creation of a new run in PROM_RUNS and a corresponding directory in FASTQDATA
           and a new run ticket in preparation for sync.
        """
        self.environment['UPSTREAM_TEST'] = f"{EXAMPLES}/upstream1"

        run_name = "20190226_TEST_00testrun"
        self.run_name = run_name # Needed for rt_cmd when copy_run() not used
        self.bm_rundriver()

        if self.verbose:
            subprocess.call(["tree", "-usa", self.temp_dir])
            subprocess.call(["head", "-v", f"{self.temp_dir}/runs/{run_name}/pipeline/type.yaml"])

        # The run is named '20190226_TEST_00testrun'. Check for dirs and symlinks.
        self.assertTrue(os.path.isdir(f"{self.temp_dir}/runs/{run_name}/pipeline"))
        self.assertTrue(os.path.isdir(f"{self.temp_dir}/fastqdata/{run_name}"))
        self.assertEqual( os.path.realpath(f"{self.temp_dir}/runs/{run_name}/pipeline/output"),
                          os.path.realpath(f"{self.temp_dir}/fastqdata/{run_name}") )
        self.assertEqual( os.path.realpath(f"{self.temp_dir}/fastqdata/{run_name}/rundata"),
                          os.path.realpath(f"{self.temp_dir}/runs/{run_name}") )

        with open(f"{self.temp_dir}/runs/{run_name}/pipeline/upstream") as fh:
            self.assertEqual(fh.read(), f"{self.environment['UPSTREAM_TEST']}/00testrun\n")

        # A new ticket should have been made
        expected_calls = self.bm.empty_calls()
        expected_calls['chgrp'] = [["-c", f"--reference={self.temp_dir}/fastqdata/{run_name}", "./pipeline"]]
        expected_calls['rt_runticket_manager.py'] = [self.rt_cmd('new', '--comment', '@???')]

        # The call to rt_runticket_manager.py is non-deterministic, so we have to doctor it...
        self.bm.last_calls['rt_runticket_manager.py'][0][-1] = re.sub(
                                    r'@\S+$', '@???', self.bm.last_calls['rt_runticket_manager.py'][0][-1] )

        self.assertEqual(self.bm.last_calls, expected_calls)

        # The STDERR from upload_report.sh and rt_runticket_manager.py should end
        # up in the per-run log.
        log_lines = slurp_file(f"{self.temp_dir}/fastqdata/{run_name}/pipeline.log")
        self.assertTrue('STDERR rt_runticket_manager.py') in log_lines
        self.assertTrue('STDERR upload_report.sh') in log_lines
        self.assertTrue('cat: pipeline/report_upload_url.txt: No such file or directory') in log_lines

        # The run should be classified as "internal"
        self.assertEqual( load_yaml(f"{self.temp_dir}/runs/{run_name}/pipeline/type.yaml"),
                          dict(type = 'internal') )

    def test_new_upstream_withbatch(self):
        """Check that setting PROM_RUNS_BATCH works.
        """
        run_name = "20190226_TEST_00testrun"
        self.environment['PROM_RUNS_BATCH'] = "month"
        self.environment['UPSTREAM_TEST'] = f"{EXAMPLES}/upstream1"

        self.bm_rundriver()

        if self.verbose:
            subprocess.call(["tree", "-usa", self.temp_dir])

        # The run is named '20190226_TEST_00testrun'. Check for dirs and symlinks.
        self.assertTrue(os.path.isdir(f"{self.temp_dir}/runs/2019-02/{run_name}/pipeline"))
        self.assertTrue(os.path.isdir(f"{self.temp_dir}/fastqdata/{run_name}"))
        self.assertEqual( os.path.realpath(f"{self.temp_dir}/runs/2019-02/{run_name}/pipeline/output"),
                          os.path.realpath(f"{self.temp_dir}/fastqdata/{run_name}") )
        self.assertEqual( os.path.realpath(f"{self.temp_dir}/fastqdata/{run_name}/rundata"),
                          os.path.realpath(f"{self.temp_dir}/runs/2019-02/{run_name}") )


    def test_new_upstream2(self):
        """A slightly more complex run with spaces in the lib name.
           Note that the spaces may well break downstream parts.
        """
        self.environment['UPSTREAM_TEST'] = f"{EXAMPLES}/upstream2"
        self.bm_rundriver()

        if self.verbose:
            subprocess.call(["tree", "-usa", self.temp_dir])

        self.assertTrue(os.path.isdir(f"{self.temp_dir}/runs/20000101_TEST_00testrun2/pipeline"))

        # Did we correctly see the three cells?
        self.assertInStdout("NEW 20000101_TEST_00testrun2 with 3 cells")

        # Is the upstream written correctly?
        with open(self.temp_dir + "/runs/20000101_TEST_00testrun2/pipeline/upstream") as fh:
            self.assertEqual(fh.read(), f"{self.environment['UPSTREAM_TEST']}/00testrun2\n")

    def test_new_upstream2_withbatch(self):
        """Same with PROM_RUNS_BATCH=year
        """
        self.environment['PROM_RUNS_BATCH'] = 'year'
        self.environment['UPSTREAM_TEST'] = f"{EXAMPLES}/upstream2"
        self.bm_rundriver()

        if self.verbose:
            subprocess.call(["tree", "-usa", self.temp_dir])

        self.assertTrue(os.path.isdir(f"{self.temp_dir}/runs/2000/20000101_TEST_00testrun2/pipeline"))

        # Did we correctly see the three cells?
        self.assertInStdout("NEW 20000101_TEST_00testrun2 with 3 cells")
        self.assertInStdout(self.environment['UPSTREAM_TEST'])
        self.assertInStdout(self.temp_dir + "/runs/2000/20000101_TEST_00testrun2")

        # Is the upstream written correctly?
        with open(self.temp_dir + "/runs/2000/20000101_TEST_00testrun2/pipeline/upstream") as fh:
            self.assertEqual(fh.read(), f"{self.environment['UPSTREAM_TEST']}/00testrun2\n")

    def test_new_without_upstream(self):
        """With a new run in PROM_RUNS that isn't found in the UPSTREAM this should trigger
           creation of a corresponding directory in FASTQDATA and a new run ticket much as
           above, but no sync as there is nothing to sync - our assumption is that this run
           should be ready for processing right away.
        """
        run_name = "20190710_LOCALTEST_00newrun"
        self.copy_run(run_name)
        self.bm_rundriver()

        if self.verbose:
            subprocess.call(["tree", "-usa", self.temp_dir])

        # Check for dirs and symlinks as above
        self.assertTrue(os.path.isdir(f"{self.temp_dir}/runs/{run_name}/pipeline"))
        self.assertTrue(os.path.isdir(f"{self.temp_dir}/fastqdata/{run_name}"))
        self.assertEqual( os.path.realpath(f"{self.temp_dir}/runs/{run_name}/pipeline/output"),
                          os.path.realpath(f"{self.temp_dir}/fastqdata/{run_name}") )
        self.assertEqual( os.path.realpath(f"{self.temp_dir}/fastqdata/{run_name}/rundata"),
                          os.path.realpath(f"{self.temp_dir}/runs/{run_name}") )

        with open(f"{self.temp_dir}/runs/{run_name}/pipeline/upstream") as fh:
            self.assertEqual(fh.read().rstrip('\n'), 'LOCAL')

        # A new ticket should have been made
        expected_calls = self.bm.empty_calls()
        expected_calls['chgrp'] = [["-c", f"--reference={self.temp_dir}/fastqdata/{run_name}", "./pipeline"]]
        expected_calls['rt_runticket_manager.py'] = [self.rt_cmd("new", "--comment", "@???")]

        # The call to rt_runticket_manager.py is non-deterministic, so we have to doctor it...
        self.bm.last_calls['rt_runticket_manager.py'][0][-1] = re.sub(
                                    r'@\S+$', '@???', self.bm.last_calls['rt_runticket_manager.py'][0][-1] )

        self.assertEqual(self.bm.last_calls, expected_calls)

    def test_empty_upstream(self):
        """With nothing to process and no upstream, we should also fail. However the error coming from
           list_remote_cells.sh shouldn't leak to STDERR as was happening in 0.6.0.
        """
        # Make a run but it's aborted so we'll ignore it.
        self.copy_run("20000101_TEST_00testrun2")
        self.touch("pipeline/aborted")

        # An empty upstream location
        self.environment['UPSTREAM_TEST'] = EXAMPLES + '/empty'

        # This should be OK
        self.bm_rundriver(expected_retval=0)

        self.assertEqual(self.bm.last_calls, self.bm.empty_calls())

        self.assertInStdout("Found 0 cells in upstream runs")
        self.assertInStdout("ls: cannot access '*/*/20??????_*_????????/other_reports': No such file or directory")

    def test_new_but_output_exists(self):
        """There should be an error if the directory in fastqdata already exists
        """
        self.copy_run("20190710_LOCALTEST_00newrun")

        os.mkdir(f"{self.temp_dir}/fastqdata/20190710_LOCALTEST_00newrun")

        # Driver should still exit cleanly
        self.bm_rundriver()
        # This should go to the main log
        self.assertInStdout("cannot create directory")

        if self.verbose:
            subprocess.call(["tree", "-usa", self.temp_dir])

        # The failed flag should be set
        self.assertTrue(os.path.exists(f"{self.temp_dir}/runs/20190710_LOCALTEST_00newrun/pipeline/failed"))
        # The source should be set to 'LOCAL'
        with open(f"{self.temp_dir}/runs/20190710_LOCALTEST_00newrun/pipeline/upstream") as fh:
            self.assertEqual(fh.read(), "LOCAL\n")

        # A new ticket should have been made, but with an error
        expected_calls = self.bm.empty_calls()
        expected_calls['rt_runticket_manager.py'] = [self.rt_cmd("failed", "--reply",
                                                                 "Failed at New_Run_Setup.\nSee log in /dev/stdout")]

        # And nothing should be written to the fastqdata dir
        self.assertEqual(os.listdir(self.temp_dir + "/fastqdata/20190710_LOCALTEST_00newrun"), [])

        self.assertEqual(self.bm.last_calls, expected_calls)

    def test_sync_needed(self):
        """A run has two cells that need synced and one completely new one.
           After the sync, we'll force one to be ready to process
           For good measure there is a space in the directory name.
        """
        # Note the upstream2 example is also used by test_run_status.py so check all is well
        # with those before trying to diagnose faults here.
        self.environment['UPSTREAM_TEST'] = f"{EXAMPLES}/upstream2"
        self.environment['SYNC_CMD'] = 'rsync =$upstream_host= =$upstream_path= =$run= =$cell='
        self.copy_run('20000101_TEST_00testrun2')

        self.touch("a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa/final_summary_PAD00000_1ea085ce.txt")

        self.bm_rundriver()

        self.assertInStdout("SYNC_NEEDED 20000101_TEST_00testrun2")
        # Because of final_summary.txt we should see this:
        self.assertTrue(os.path.exists(self.run_path + "/pipeline/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa.synced"))

        expected_calls = self.bm.empty_calls()
        rsync_first_bit = ["==", f"={EXAMPLES}/upstream2/00testrun2=", "=20000101_TEST_00testrun2="]
        expected_calls['rsync'] = [ rsync_first_bit + ["=a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa="],
                                    rsync_first_bit + ["=a test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb="],
                                    rsync_first_bit + ["=another test/20000101_0000_3-C1-C1_PAD00000_cccccccc="] ]
        self.assertEqual(self.bm.last_calls, expected_calls)

    def test_log_bug(self):
        """I had a bug where if there were multiple new upstream runs the logs would both go to the
           first of them. Not good.
        """
        self.environment['UPSTREAM_TEST'] = f"{EXAMPLES}/upstream3"

        self.bm_rundriver()

        if self.verbose:
            subprocess.call(["tree", "-usa", self.temp_dir])

        # The run will be named '20190226_TEST_00testrun'. Check for dirs and symlinks.
        log1 = slurp_file(f"{self.temp_dir}/fastqdata/20190226_TEST_00testrun/pipeline.log")
        log2 = slurp_file(f"{self.temp_dir}/fastqdata/20190226_TEST_00testruncopy/pipeline.log")

        self.assertEqual(len(log1), len(log2))

    def test_log_bug2(self):
        """The same bug as above when one run is incomplete and another is ready to process
        """
        self.environment['UPSTREAM_TEST'] = EXAMPLES + '/upstream2'
        self.environment['SYNC_CMD'] = 'rsync =$upstream_host= =$upstream_path= =$run= =$cell='
        self.copy_run("20000101_TEST_00testrun2")
        run_path_1 = self.run_path

        # Now add a run which is incomplete
        self.copy_run('20190710_LOCALTEST_00missingfile')
        os.makedirs(os.path.join(self.run_path, "pipeline/output"))
        run_path_2 = self.run_path

        # Ensure any processing fails
        self.bm.add_mock('make_summary.py', fail=False)
        self.bm.add_mock('Snakefile.main', fail=True)

        self.bm_rundriver()
        self.assertInStdout("INCOMPLETE 20190710_LOCALTEST_00missingfile")
        self.assertInStdout("SYNC_NEEDED 20000101_TEST_00testrun2")

        # A correctly-named plog should now appear in both
        lines_in_log1 = slurp_file(os.path.join(run_path_1, "pipeline", "output", "sync_from_upstream.log"))
        self.assertFalse(os.path.exists(os.path.join(run_path_1, "pipeline", "output", "pipeline.log")))

        lines_in_log2 = slurp_file(os.path.join(run_path_2, "pipeline", "output", "pipeline.log"))
        self.assertFalse(os.path.exists(os.path.join(run_path_2, "pipeline", "output", "sync_from_upstream.log")))

        # Neither should be empty
        self.assertTrue(lines_in_log1)
        self.assertTrue(lines_in_log2)

    def test_sync_needed_withbatch(self):
        """Same with PROM_RUNS_BATCH=year
        """
        run_name = "20000101_TEST_00testrun2"
        self.environment['PROM_RUNS_BATCH'] = 'year'
        self.environment['UPSTREAM_TEST'] = EXAMPLES + '/upstream2'
        self.environment['SYNC_CMD'] = 'rsync "$upstream_host" "$upstream_path" "$run" "$run_dir" "$run_dir_full" "$cell"'
        self.copy_run(run_name, subdir=run_name[:4])

        #self.touch("a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa/final_summary.txt")
        self.touch("a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa/final_summary_PAD00000_1ea085ce.txt")

        self.bm_rundriver()

        self.assertInStdout(f"SYNC_NEEDED {run_name}")
        # Because of final_summary.txt we should see this:
        self.assertTrue(os.path.exists(self.run_path + "/pipeline/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa.synced"))

        expected_calls = self.bm.empty_calls()
        rsync_first_bit = [ "",                                 # No upstream host
                            f"{EXAMPLES}/upstream2/00testrun2", # Upstream source of example run
                            f"{run_name}",                      # The name of the run
                            f"{run_name[:4]}/{run_name}",       # The target directory, including the year
                            self.run_path                       # The full target directory
                          ]
        expected_calls['rsync'] = [ rsync_first_bit + ["a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa"],
                                    rsync_first_bit + ["a test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb"],
                                    rsync_first_bit + ["another test/20000101_0000_3-C1-C1_PAD00000_cccccccc"] ]
        self.assertEqual(self.bm.last_calls, expected_calls)

    def test_run_complete(self):
        """Same run as above, but skip past the syncing part.
           When the pipeline runs again it should notify the run as complete and kick off
           processing and do all the other stuff.
        """
        self.copy_run('20000101_TEST_00testrun2')
        self.touch("pipeline/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa.synced")
        self.touch("pipeline/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb.synced")

        self.bm_rundriver()
        self.assertInStdout("CELL_READY 20000101_TEST_00testrun2")
        self.assertTrue(os.path.exists(f"{self.run_path}/pipeline/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa.done"))
        self.assertTrue(os.path.exists(f"{self.run_path}/pipeline/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb.done"))
        self.assertFalse(os.path.exists(f"{self.run_path}/pipeline/failed"))

        # Doctor non-deterministic calls to rt_runticket_manager.py
        for i, c in enumerate(self.bm.last_calls['rt_runticket_manager.py']):
            self.bm.last_calls['rt_runticket_manager.py'][i][-1] = re.sub( r'@\S+$', '@???', c[-1] )

        expected_calls = self.bm.empty_calls()
        expected_calls['scan_cells.py'] = [[ "-m",
                                             "-r",
                                                "a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa",
                                                "a test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb",
                                             "-c",
                                                "a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa",
                                                "a test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb" ]]
        expected_calls['Snakefile.main'] = [self.snake_targets]
        expected_calls['upload_report.sh'] = [[ self.run_path + "/pipeline/output" ]]
        expected_calls['rt_runticket_manager.py'] = [self.rt_cmd("processing", "--reply",
                                                                 "All 2 cells have run on the instrument. Full report will follow soon."),
                                                     self.rt_cmd("processing", "--comment", "@???"),
                                                     self.rt_cmd("Finished all cells", "--reply", "@???" )]
        expected_calls['del_remote_cells.sh'] = [[ "/DUMMY/PATH/20000101_TEST_00testrun2",
                                                   "a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa",
                                                   "a test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb" ]]

        self.assertEqual(self.bm.last_calls, expected_calls)

    def test_run_partial(self):
        """Same run as above, but only one cell is ready.
           When the pipeline runs again it should NOT notify the run as complete but the one cell
           should be processed (higher priority than starting the sync).
        """
        self.copy_run('20000101_TEST_00testrun2')
        self.touch("pipeline/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa.synced")

        self.bm_rundriver()
        self.assertInStdout("CELL_READY 20000101_TEST_00testrun2")

        # Doctor non-deterministic calls to rt_runticket_manager.py
        for i, c in enumerate(self.bm.last_calls['rt_runticket_manager.py']):
            self.bm.last_calls['rt_runticket_manager.py'][i][-1] = re.sub( r'@\S+$', '@???', c[-1] )

        expected_calls = self.bm.empty_calls()
        expected_calls['scan_cells.py'] = [[ "-m",
                                             "-r",
                                                "a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa",
                                             "-c",
                                                "a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa",
                                                "a test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb" ]]
        expected_calls['Snakefile.main'] = [self.snake_targets]
        expected_calls['upload_report.sh'] = [[ self.run_path + "/pipeline/output" ]]
        expected_calls['rt_runticket_manager.py'] = [self.rt_cmd("processing", "--comment", "@???"),
                                                     self.rt_cmd("Finished cell", "--reply", "@???")]
        expected_calls['del_remote_cells.sh'] = [[ "/DUMMY/PATH/20000101_TEST_00testrun2",
                                                   "a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa" ]]

        self.assertEqual(self.bm.last_calls, expected_calls)

    def test_run_complete_rtfail(self):
        """Same as test_run_complete, but messaging to RT fails.
           The run should press on up to the final stage but should then fail and
           not del_remote_cells
        """
        self.copy_run('20000101_TEST_00testrun2')
        self.touch("pipeline/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa.synced")
        self.touch("pipeline/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb.synced")

        # When the driver can't report a failure to RT, it will log an error to STDERR so that
        # the CRON can send us warning messages directly.
        self.bm.add_mock('rt_runticket_manager.py', fail=True)
        self.bm_rundriver(check_stderr=False)

        self.assertInStdout("CELL_READY 20000101_TEST_00testrun2")
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
        expected_calls['scan_cells.py'] = [[ "-m",
                                             "-r",
                                                "a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa",
                                                "a test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb",
                                             "-c",
                                                "a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa",
                                                "a test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb" ]]
        expected_calls['Snakefile.main'] = [self.snake_targets]
        expected_calls['upload_report.sh'] = [[ self.run_path + "/pipeline/output" ]]
        # Is this right? The pipeline tries to report the RT failure to RT and only then does it admit defeat and
        # report the error to STDERR. I gues it's OK.
        expected_calls['rt_runticket_manager.py'] = [self.rt_cmd("processing", "--reply",
                                                                 "All 2 cells have run on the instrument."
                                                                 " Full report will follow soon."),
                                                     self.rt_cmd("processing", "--comment", "@???"),
                                                     self.rt_cmd("Finished all cells", "--reply", "@???"),
                                                     self.rt_cmd("failed", "--reply",
                                                                 "Failed at Reporting for cells [\n"
                                                                 "\ta test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa,\n"
                                                                 "\ta test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb\n"
                                                                 "].\n"
                                                                 f"See log in {self.run_path}/pipeline/output/pipeline.log")]
        expected_calls['del_remote_cells.sh'] = []

        self.assertEqual(self.bm.last_calls, expected_calls)

    def test_run_complete_uploadfail(self):
        """Same as test_run_complete_rtfail, but upload of report fails.
           The run should notify RT (which will work) but then end in a failed
           state because of the upload failure.
        """
        self.copy_run("20000101_TEST_00testrun2")
        self.touch("pipeline/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa.synced")
        self.touch("pipeline/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb.synced")

        # Make the report uploader fail
        self.bm.add_mock('upload_report.sh', fail=True, side_effect="echo Error in upload_report.sh >&2")
        self.bm_rundriver()

        self.assertInStdout("CELL_READY 20000101_TEST_00testrun2")
        self.assertInStdout("Processing completed but failed to upload the report.")
        # We've already asserted that STDERR is empty.

        self.assertFalse(os.path.exists(self.run_path + "/pipeline/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa.done"))
        self.assertFalse(os.path.exists(self.run_path + "/pipeline/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb.done"))
        self.assertTrue(os.path.exists(self.run_path + "/pipeline/failed"))

        # Doctor non-deterministic calls to rt_runticket_manager.py
        rtcalls = self.bm.last_calls['rt_runticket_manager.py']
        for i in range(len(rtcalls)):
            rtcalls[i][-1] = re.sub( r'@\S+$', '@???', rtcalls[i][-1] )

        expected_calls = self.bm.empty_calls()
        expected_calls['scan_cells.py'] = [[ "-m",
                                             "-r",
                                                "a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa",
                                                "a test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb",
                                             "-c",
                                                "a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa",
                                                "a test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb" ]]
        expected_calls['Snakefile.main'] = [self.snake_targets]
        expected_calls['upload_report.sh'] = [[ self.run_path + "/pipeline/output" ]]
        expected_calls['rt_runticket_manager.py'] = [self.rt_cmd("processing", "--reply",
                                                                 "All 2 cells have run on the instrument."
                                                                 " Full report will follow soon."),
                                                     self.rt_cmd("processing", "--comment", "@???"),
                                                     self.rt_cmd("failed", "--reply",
                                                                 "Failed at Reporting for cells [\n"
                                                                 "\ta test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa,\n"
                                                                 "\ta test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb\n"
                                                                 "].\n"
                                                                 f"See log in {self.run_path}/pipeline/output/pipeline.log")]
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
        self.copy_run("20000101_TEST_00testrun2")
        self.touch("pipeline/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa.synced")

        # When the driver can't report a failure to RT, it will log an error to STDERR so that
        # the CRON can send us warning messages directly.
        self.bm.add_mock('rt_runticket_manager.py', fail=True)
        self.bm_rundriver(check_stderr=False)

        self.assertInStdout("CELL_READY 20000101_TEST_00testrun2")
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
        expected_calls['scan_cells.py'] = [[ "-m",
                                             "-r",
                                                "a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa",
                                             "-c",
                                                "a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa",
                                                "a test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb" ]]
        expected_calls['Snakefile.main'] = [self.snake_targets]
        expected_calls['upload_report.sh'] = [[ self.run_path + "/pipeline/output" ]]
        expected_calls['rt_runticket_manager.py'] = [ self.rt_cmd("processing", "--comment", "@???"),
                                                      self.rt_cmd("Finished cell", "--reply", "@???"),
                                                      self.rt_cmd("failed", "--reply",
                                                                  "Failed at Reporting for cells [\n"
                                                                  "\ta test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa\n"
                                                                  "].\n"
                                                                  f"See log in {self.run_path}/pipeline/output/pipeline.log") ]
        expected_calls['del_remote_cells.sh'] = []

        self.assertEqual(self.bm.last_calls, expected_calls)

if __name__ == '__main__':
    unittest.main()
