#!/usr/bin/env python3

import unittest
import sys, os
import glob
from tempfile import mkdtemp
from shutil import rmtree, copytree
from pprint import pprint
import logging as L
from unittest.mock import Mock, patch
from io import StringIO

# Adding this to sys.path makes the test work if you just run it directly.
with patch('sys.path', new=['.'] + sys.path):
    from run_status import RunStatus, parse_remote_cell_info

EXAMPLES = os.path.dirname(__file__) + '/examples'
VERBOSE = os.environ.get('VERBOSE', '0') != '0'

L.basicConfig(level=(L.DEBUG if VERBOSE else L.WARNING))

class T(unittest.TestCase):

    #Helper functions:
    def use_run(self, run_id, copy=False, make_run_info=True):
        """Inspect a run.
           If copy=True, copies the selected run into a temporary folder first.
           Sets self.current_run to the run id and
           self.run_dir to the run dir, temporary or otherwise.
           Also returns a RunStatus object for you.
        """
        self.cleanup_run()

        # Make a temp dir if needed
        if copy:
            self.tmp_dir = mkdtemp()
            self.run_dir = self.tmp_dir + '/runs'
            os.mkdir(self.run_dir)

            # Clone the run folder into it
            with patch('shutil.copystat', lambda *a, **kw: True):
                copytree( os.path.join(EXAMPLES, 'runs', run_id),
                          os.path.join(self.run_dir, run_id),
                          symlinks=True )
        else:
            self.run_dir = EXAMPLES + '/runs'

        # Set the current_run variable
        self.current_run = run_id
        self.current_run_dir = os.path.join(self.run_dir, run_id)

        # Presumably we want to inspect the new run, so do that too.
        # If you want to change files around or add upstream info, do that then make a
        # new RunStatus by copying the line below.
        if make_run_info:
            return RunStatus(os.path.join(self.current_run_dir))

    def cleanup_run(self):
        """If self.tmp_dir has been set, delete the temporary
           folder. Either way, clear the currently set run.
        """
        if vars(self).get('tmp_dir'):
            rmtree(self.tmp_dir)

        self.run_dir = self.tmp_dir = None
        self.current_run = None

    def tearDown(self):
        """ Avoid leaving temp files around.
        """
        self.cleanup_run()

    def md(self, fp):
        """ Make a directory in the right location
        """
        os.makedirs(os.path.join(self.current_run_dir, fp))

    def touch(self, fp, content="meh"):
        with open(os.path.join(self.current_run_dir, fp), 'w') as fh:
            print(content, file=fh)

    def rm(self, dp):
        # Careful with this one, it's basically rm -rf
        try:
            rmtree(os.path.join(self.current_run_dir, dp))
        except NotADirectoryError:
            os.remove(os.path.join(self.current_run_dir, dp))
    # And the tests...

    def test_run_new(self):
        """ A totally new run.
        """
        run_info = self.use_run('201907010_LOCALTEST_newrun')

        self.assertEqual( run_info.get_status(), 'new' )
        self.assertEqual( run_info.get_instrument(), 'LOCALTEST' )
        self.assertEqual( run_info.remote_loc, None )

        # I should get the same via YAML
        self.assertEqual( dictify(run_info.get_yaml())['PipelineStatus:'], 'new' )
        self.assertEqual( dictify(run_info.get_yaml())['Upstream:'], 'LOCAL' )
        self.assertEqual( dictify(run_info.get_yaml())['Cells:'], 'testlib/20190710_1723_2-A5-D5_PAD38578_c6ded78b' )
        self.assertEqual( dictify(run_info.get_yaml())['CellsPending:'], 'testlib/20190710_1723_2-A5-D5_PAD38578_c6ded78b' )

        # This run has 1 cell
        self.assertCountEqual( run_info.get_cells(), "testlib/20190710_1723_2-A5-D5_PAD38578_c6ded78b".split() )

        # None are ready
        self.assertCountEqual( run_info.get_cells_in_state(run_info.CELL_READY), [] )

    def test_with_without_upstream(self):
        """A run that has corresponding upstream info. When the cells are listed
           in the upstream the status should switch from 'incomplete' to 'sync_needed'
           and the internal status should chenge from INCOMPLETE to PENDING
        """
        run_info = self.use_run('20000101_TEST_testrun2', copy=True)

        # This should have two incomplete cells, and thus be in status incomplete
        self.assertEqual( run_info.get_status(), 'incomplete' )
        self.assertEqual( run_info.get_cells_in_state(run_info.CELL_INCOMPLETE), [
                                'a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa',
                                'a test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb' ] )
        self.assertEqual( run_info.get_cells_in_state(run_info.CELL_PENDING), [] )

        # But for the report, incomplete gets merged into pending
        self.assertEqual( dictify(run_info.get_yaml())['CellsPending:'],
                                'a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa\t'
                                'a test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb' )

        # Now if I redo the run_info with relevant upstream
        run_info = RunStatus( os.path.join(self.current_run_dir),
                            upstream = { "20000101_TEST_testrun2": {
                                            "loc": "xxx",
                                            "cells": set([ "a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa",
                                                           "a test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb" ]) } } )

        # Now those cells should be pending
        self.assertEqual( run_info.get_status(), 'sync_needed' )
        self.assertEqual( run_info.get_cells_in_state(run_info.CELL_PENDING), [
                                'a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa',
                                'a test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb' ] )
        self.assertEqual( run_info.get_cells_in_state(run_info.CELL_INCOMPLETE), [] )

        # But for the report, incomplete gets merged into pending as before
        self.assertEqual( dictify(run_info.get_yaml())['CellsPending:'],
                                'a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa\t'
                                'a test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb' )

        # Now let's mark those two cells as complete
        self.touch("pipeline/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa.done")
        self.touch("pipeline/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb.done")

        # Run should be complete
        run_info = RunStatus( os.path.join(self.current_run_dir) )
        self.assertEqual( run_info.get_status(), 'complete' )

        # If I add an unrecognised cell to the upstream that should be pending,
        # and push us back to sync_needed
        run_info = RunStatus( os.path.join(self.current_run_dir),
                            upstream = { "20000101_TEST_testrun2": {
                                            "loc": "xxx",
                                            "cells": set([ "a test lib/TEST123" ]) } } )

        self.assertEqual( run_info.get_status(), 'sync_needed' )

        self.assertEqual( run_info.get_cells_in_state(run_info.CELL_PROCESSED), [
                                'a test lib/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa',
                                'a test lib/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb' ] )
        self.assertEqual( run_info.get_cells_in_state(run_info.CELL_NEW), [
                                'a test lib/TEST123' ] )
        self.assertEqual( dictify(run_info.get_yaml())['CellsPending:'],
                                'a test lib/TEST123' )



    def test_parse_remote_cell_info(self):
        """Test that we can get info from list_remote_cells.sh
           This reads stdin directly so mock it
        """
        # Empty case
        with patch('sys.stdin', new=StringIO("")):
            self.assertEqual(parse_remote_cell_info(), dict())

        with patch('sys.stdin', new=StringIO("\n")):
            self.assertEqual(parse_remote_cell_info(), dict())

        # A pair of cells
        ui = "20190322_EGS1_11685BN\tprom@promethion:/data/20190322_11685BN\t11685BN0002L01_unsheare/XXX\n" + \
             "20190322_EGS1_11685BN\tprom@promethion:/data/20190322_11685BN\t11685BN0002L01_unsheare/YYY"
        with patch('sys.stdin', new=StringIO(ui)):
            self.assertEqual(parse_remote_cell_info(), {
                                    "20190322_EGS1_11685BN": {
                                        "loc": "prom@promethion:/data/20190322_11685BN",
                                        "cells": set([ "11685BN0002L01_unsheare/XXX",
                                                       "11685BN0002L01_unsheare/YYY" ]) } })

    def test_sync_in_progress(self):
        """Test for bug noted on 30/7 - a run with sync in progress should appear in this state even if
           there is no upstream info provided.
        """
        run_info = self.use_run('20000101_TEST_testrun2', copy=True)
        self.assertEqual( run_info.get_status(), 'incomplete' )

        # If I say that both cells on this run are done, but supply a third then it should be in
        # sync_needed status.
        self.touch("pipeline/20000101_0000_1-A1-A1_PAD00000_aaaaaaaa.done")
        self.touch("pipeline/20000101_0000_2-B1-B1_PAD00000_bbbbbbbb.done")
        run_info = RunStatus( os.path.join(self.current_run_dir) )
        self.assertEqual( run_info.get_status(), 'complete' )

        run_info = RunStatus( os.path.join(self.current_run_dir),
                            upstream = { "20000101_TEST_testrun2": {
                                            "loc": "xxx",
                                            "cells": set([ "a test lib/20000101_0000_3-C1-C1_PAD00000_cccccccc" ]) } } )
        self.assertEqual( run_info.get_status(), 'sync_needed' )

        # Now for the real test - pretend I've started syncing
        self.touch("pipeline/sync.started")

        # Now the status should be syncing whether or not I provide the upstream
        run_info = RunStatus( os.path.join(self.current_run_dir),
                            upstream = { "20000101_TEST_testrun2": {
                                            "loc": "xxx",
                                            "cells": set([ "a test lib/20000101_0000_3-C1-C1_PAD00000_cccccccc" ]) } } )
        self.assertEqual( run_info.get_status(), 'syncing' )

        run_info = RunStatus( os.path.join(self.current_run_dir) )
        self.assertEqual( run_info.get_status(), 'syncing' )


def dictify(s):
    """ Very very dirty minimal YAML parser is OK for testing.
    """
    return dict( l.split(' ', 1) for l in s.split('\n') )

if __name__ == '__main__':
    unittest.main()

