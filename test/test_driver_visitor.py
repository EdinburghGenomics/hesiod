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

from test_driver_base import slurp_file, TestDriverBase

class T(TestDriverBase):

    # See TestDriverBase for all the utility stuff
    def __init__(self, *args):
        super().__init__(*args)
        self.example_runs = os.path.join(self.examples, "visitor_runs")

        # Mock 'env' as it's used to make calls to the toolbox
        self.progs_to_mock['env'] = None

    def test_new_test_run(self):
        """A run recognised as nither visitor nor internal should be synced
           but processing complete flowcells is a no-op.
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

        # A new ticket should have been made
        self.assertTrue(False and "Ticket should be opened on alternative RT queue")

        expected_calls = self.bm.empty_calls()
        expected_calls['chgrp'] = [["-c", f"--reference={self.temp_dir}/fastqdata/{run_name}", "./pipeline"]]
        expected_calls['rt_runticket_manager.py'] = [self.rt_cmd("new", "--comment", "@???")]

        # The call to rt_runticket_manager.py is non-deterministic, so we have to doctor it...
        self.bm.last_calls['rt_runticket_manager.py'][0][-1] = re.sub(
                                    r'@\S+$', '@???', self.bm.last_calls['rt_runticket_manager.py'][0][-1] )

        self.assertEqual(self.bm.last_calls, expected_calls)

        # Run should be judged to be a test run
        self.assertEqual( load_yaml(f"{self.temp_dir}/runs/{run_name}/pipeline/type.yaml"),
                          dict(type = 'test') )

    def test_new_visitor_run(self):

        run_name = "20230101_ONT1_v_tbooth2_test1"
        self.copy_run(run_name)
        self.bm_rundriver()

        if self.verbose:
            subprocess.call(["tree", "-usa", self.temp_dir])

        # Check for dirs and symlinks (is redundant so removed)

        # A new ticket should have been made
        self.assertTrue(False and "Ticket should be opened on alternative RT queue")

        expected_calls = self.bm.empty_calls()
        expected_calls['chgrp'] = [["-c", f"--reference={self.temp_dir}/fastqdata/{run_name}", "./pipeline"]]
        expected_calls['rt_runticket_manager.py'] = [self.rt_cmd("new", "--comment", "@???")]

        # The call to rt_runticket_manager.py is non-deterministic, so we have to doctor it...
        self.bm.last_calls['rt_runticket_manager.py'][0][-1] = re.sub(
                                    r'@\S+$', '@???', self.bm.last_calls['rt_runticket_manager.py'][0][-1] )

        self.assertEqual(self.bm.last_calls, expected_calls)

        # Run should be judged to be a visitor run
        self.assertEqual( load_yaml(f"{self.temp_dir}/runs/{run_name}/pipeline/type.yaml"),
                          dict(type = 'visitor etc.') )


    def test_visitor_cell_complete(self):

        run_name = "20230101_ONT1_v_tbooth2_test1"
        self.copy_run(run_name)
        self.bm_rundriver()

        # And this should deliver the cells
        self.bm_rundriver()

        expected_calls = self.bm.empty_calls()
        expected_calls['env'] = [['deliver_visitor_cells', 'x', 'y']]
        self.assertEqual(self.bm.last_calls, expected_calls)


