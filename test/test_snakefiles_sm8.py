#!/usr/bin/env python3
# vim: set fileencoding=utf-8 :
import sys, os, re
import unittest
from unittest.mock import patch
from glob import glob
from io import StringIO
import logging
from pprint import pprint

import snakemake
bad_snakemake_version = snakemake.__version__ < "8.0.0"
if not bad_snakemake_version:
    # Importing this way gets past the "cannot import...from partially initialized module" error.
    import snakemake.api, snakemake.sourcecache, snakemake.workflow
    from snakemake.settings.types import ( ConfigSettings, ResourceSettings,
                                           WorkflowSettings, StorageSettings )

VERBOSE = os.environ.get('VERBOSE', '0') != '0'

@unittest.skipIf(bad_snakemake_version, reason="Test is for Snakemake 8")
class T(unittest.TestCase):
    """ Load all the snakefiles just to check I haven't let in some silly syntax error.
    """
    def setUp(self):
        os.environ['TOOLBOX'] = '/'

        #Prevent the logger from printing messages - I like my tests to look pretty.
        for handler in list(logging.root.handlers):
            logging.root.removeHandler(handler)

        if VERBOSE:
            logging.getLogger().setLevel(logging.DEBUG)
        else:
            logging.getLogger().setLevel(logging.CRITICAL)

    @patch('sys.stderr', new_callable=StringIO)
    @patch('sys.stdout', new_callable=StringIO)
    def syntax_check(self, sf, mock_stdout, mock_stderr):
        """ Check that I can load a given workflow OK
        """
        cs = ConfigSettings(config = dict( workdir = '.',
                                           rundir  = '.',
                                           ignore_missing = True ))
        rs = ResourceSettings()
        ws = WorkflowSettings()
        ss = StorageSettings()

        wf = snakemake.workflow.Workflow( config_settings = cs,
                                          resource_settings = rs,
                                          workflow_settings = ws,
                                          storage_settings = ss )
        wf.include(sf)

        self.assertTrue(len(wf.rules) > 1)

        # Avoids a resource warning
        try:
            wf.sourcecache.runtime_cache.cleanup()
        except Exception:
            pass

# This bit copied from test_base_mask_extractor in Illuminatus...
# Now add the tests dynamically
for sf in "main rundata blob".split():
    snakefile = os.path.join(os.path.dirname(__file__), '..', f"Snakefile.{sf}")

    # Note the slightly contorted double-lambda syntax to make the closure.
    sfname = os.path.basename(snakefile).split('.')[1]
    setattr(T, 'test_sf_' + sfname, (lambda d: lambda self: self.syntax_check(d))(snakefile))


if __name__ == '__main__':
    unittest.main()
