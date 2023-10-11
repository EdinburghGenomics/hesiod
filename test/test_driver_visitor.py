#!/usr/bin/env python3

"""Tests specific to visitor mode operation of driver.sh
"""

import unittest
import sys, os, re
from unittest.mock import patch

import subprocess
from tempfile import mkdtemp
from shutil import rmtree, copytree
from glob import glob

from test_driver_base import slurp_file, TestDriverBase, load_yaml

class T(TestDriverBase):

    # See TestDriverBase for all the utility stuff
    def __init__(self, *args):
        super().__init__(*args)
        self.example_runs = os.path.join(self.examples, "visitor_runs")

        self.progs_to_mock['Snakefile.checksummer'] = None

        # Mock 'env' as it's used to make calls to the toolbox
        self.progs_to_mock['env'] = None

    def rt_cmd(self, *args, **kwargs):
        """Get the expected args to rt_runticket_manager.py

           Override base to set "-Q promrun_visitor"
        """
        rtq = kwargs.get("alt_queue", "visitor")

        return [*f"-r {self.run_name} -Q promrun_{rtq} -P Experiment --subject".split(), *args]

    def test_new_test_run(self):
        """A run recognised as neither visitor nor internal should be synced
           but processing any complete flowcells is a no-op.

           Assume the upstream will work as with internal runs and just have
           this as a LOCAL run.
        """
        run_name = "20230101_ONT1_somerun"
        self.copy_run(run_name)
        self.bm_rundriver()

        if self.verbose:
            subprocess.call(["tree", "-usa", self.temp_dir])

        # Check for dirs and symlinks
        self.assertTrue(os.path.isdir(f"{self.temp_dir}/runs/{run_name}/pipeline"))
        self.assertTrue(os.path.isdir(f"{self.temp_dir}/fastqdata/{run_name}"))
        self.assertEqual( os.path.realpath(f"{self.temp_dir}/runs/{run_name}/pipeline/output"),
                          os.path.realpath(f"{self.temp_dir}/fastqdata/{run_name}") )
        self.assertEqual( os.path.realpath(f"{self.temp_dir}/fastqdata/{run_name}/rundata"),
                          os.path.realpath(f"{self.temp_dir}/runs/{run_name}") )

        with open(f"{self.temp_dir}/runs/{run_name}/pipeline/upstream") as fh:
            self.assertEqual(fh.read().rstrip('\n'), 'LOCAL')

        expected_calls = self.bm.empty_calls()
        expected_calls['chgrp'] = [["-c", f"--reference={self.temp_dir}/fastqdata/{run_name}", "./pipeline"]]
        expected_calls['rt_runticket_manager.py'] = [self.rt_cmd( "new", "--comment", "@???",
                                                                  alt_queue = "test" )]

        # The call to rt_runticket_manager.py is non-deterministic, so we have to doctor it...
        self.bm.last_calls['rt_runticket_manager.py'][0][-1] = re.sub(
                                    r'@\S+$', '@???', self.bm.last_calls['rt_runticket_manager.py'][0][-1] )

        self.assertEqual(self.bm.last_calls, expected_calls)

        # Run should be judged to be a test run
        self.assertEqual( load_yaml(f"{self.temp_dir}/runs/{run_name}/pipeline/type.yaml"),
                          dict(type = 'test') )

        # If this file had been there initially then the next run of the driver would process
        # the cells, but as it is the run will only mark the cell as ready.
        self.touch("sampleA/20230101_1111_2G_PAQ12345_zzzzzzzz/final_summary_xxx_yyy.txt")
        self.bm_rundriver()
        self.assertInStdout("1 cells in this experiment are now ready for processing")

        # This should not do anything when a cell is ready, aside from acknowledging and
        # setting the pipeline status to DONE
        self.bm_rundriver()
        self.assertInStdout(f"CELL_READY {run_name}. But EXPT_TYPE is test. Taking no action.")

        # And this should do nothing at all
        self.bm_rundriver()
        self.assertInStdout(f"{run_name} with 1 cell(s) and status=complete")

    def test_new_visitor_run(self):

        run_name = "20230101_ONT1_v_tbooth2_test1"
        self.copy_run(run_name)
        self.bm_rundriver()

        if self.verbose:
            subprocess.call(["tree", "-usa", self.temp_dir])

        # Check for dirs and symlinks (is redundant so removed)

        # A new ticket should have been made
        expected_calls = self.bm.empty_calls()
        expected_calls['chgrp'] = [["-c", f"--reference={self.temp_dir}/fastqdata/{run_name}", "./pipeline"]]
        expected_calls['rt_runticket_manager.py'] = [self.rt_cmd("new", "--comment", "@???")]

        # The call to rt_runticket_manager.py is non-deterministic, so we have to doctor it...
        self.bm.last_calls['rt_runticket_manager.py'][0][-1] = re.sub(
                                    r'@\S+$', '@???', self.bm.last_calls['rt_runticket_manager.py'][0][-1] )

        self.assertEqual(self.bm.last_calls, expected_calls)

        # Run should be judged to be a visitor run
        self.assertEqual( load_yaml(f"{self.temp_dir}/runs/{run_name}/pipeline/type.yaml"),
                          dict(type="visitor", uid="tbooth2") )


    def test_visitor_cell_complete(self):

        run_name = "20230101_ONT1_v_tbooth2_test1"
        self.copy_run(run_name)
        self.touch("sample1/20230101_1111_2G_PAQ12345_aaaaaaaa/final_summary_xxx_yyy.txt")
        self.touch("sample1/20230101_1111_2G_PAQ12345_bbbbbbbb/final_summary_xxx_yyy.txt")
        self.touch("sample2/20230101_1111_2G_PAQ12345_cccccccc/final_summary_xxx_yyy.txt")
        self.bm_rundriver() # See tests above

        if self.verbose:
            subprocess.call(["tree", "-usa", self.temp_dir])

        # And this should deliver the cells immediately, since I added the summaries
        # before the first driver run.
        self.bm_rundriver()
        self.assertInStdout(f"CELL_READY {run_name}. Auto-delivering 3 visitor cells")

        expected_calls = self.bm.empty_calls()
        expected_calls['env'] = [['deliver_visitor_cells', 'x', 'y']]
        self.assertEqual(self.bm.last_calls, expected_calls)

        # After this, once cell is left incomplete
        self.bm_rundriver()
        self.assertInStdout(f"{run_name} with 4 cell(s) and status=incomplete")

        # So finish that one too
        self.bm_rundriver()
        self.assertInStdout(f"CELL_READY {run_name}. Auto-delivering 1 visitor cells")

        self.assertInStdout(f"{run_name} with 4 cell(s) and status=complete")
