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
        # If you want to change files around, do that then make a new RunStatus
        # by copying the line below.
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
        with open(os.path.join(self.run_dir_dir, fp), 'w') as fh:
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

    def test_parse_remote_cell_info(self):
        """Test that we can get info from list_remote_cells.sh
           This reads stdin directly so mock it
        """
        with patch('sys.stdin', new=StringIO("")):
            self.assertEqual(parse_remote_cell_info(), dict())

        with patch('sys.stdin', new=StringIO("\n")):
            self.assertEqual(parse_remote_cell_info(), dict())

def dictify(s):
    """ Very very dirty minimal YAML parser is OK for testing.
    """
    return dict( l.split(' ', 1) for l in s.split('\n') )

if __name__ == '__main__':
    unittest.main()

