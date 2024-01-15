#!/usr/bin/env python3

"""Test stuff in hesiod/__init__.py"""

import sys, os, re
import unittest
import logging
from collections import OrderedDict, namedtuple
from datetime import datetime, timezone
from dateutil.tz.tz import tzutc
from pprint import pprint
from textwrap import dedent as dd

DATA_DIR = os.path.abspath(os.path.dirname(__file__) + '/examples')
VERBOSE = os.environ.get('VERBOSE', '0') != '0'

from hesiod import ( parse_cell_name, load_final_summary, abspath, groupby, glob,
                     find_sequencing_summary, find_summary, load_yaml, dump_yaml,
                     empty_sc_data, od_key_replace )

class T(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        #Prevent the logger from printing messages - I like my tests to look pretty.
        if VERBOSE:
            logging.getLogger().setLevel(logging.DEBUG)
        else:
            logging.getLogger().setLevel(logging.CRITICAL)

    def setUp(self):
        # See the errors in all their glory
        self.maxDiff = None

    ### THE TESTS ###
    def test_parse_cell_name(self):

        res = parse_cell_name('20210520_EGS1_16031BA', '16031BApool01/20210520_1105_2-E1-H1_PAG23119_76e7e00f')
        self.assertEqual(type(res), OrderedDict)
        self.assertEqual(dict(res), dict(
                    Experiment = '20210520_EGS1_16031BA',
                    Cell       = '16031BApool01/20210520_1105_2-E1-H1_PAG23119_76e7e00f',
                    Pool       = '16031BApool01',
                    Date       = '20210520',
                    Number     = '1105',
                    Slot       = '2-E1-H1',
                    CellID     = 'PAG23119',
                    Checksum   = '76e7e00f',
                    Project    = '16031',
                    Base       = '16031BApool01/20210520_1105_2-E1-H1_PAG23119_76e7e00f/'
                                   '20210520_EGS1_16031BA_16031BApool01_PAG23119_76e7e00f' ) )

        # There should be a couple of sanity checks
        with self.assertRaises(ValueError): parse_cell_name('A/B', 'C/D')
        with self.assertRaises(ValueError): parse_cell_name('A', 'B/C/D')

    def test_load_final_summary(self):

        example_file = os.path.join(DATA_DIR, "final_summary_PAK00383_564d5253.txt")

        # The datetime comparison needs to use tzutc() even though timezone.utc is functionally equivalent,
        # because of the way datetutil operates.

        self.assertEqual( load_final_summary(example_file),
                          dict( instrument          = "PCT0112",
                                position            = "2-E11-H11",
                                flow_cell_id        = "PAK00383",
                                sample_id           = "21600MP_2_0001-0004",
                                protocol_group_id   = "21600MP_2",
                                protocol            = "sequencing/sequencing_PRO002_DNA:FLO-PRO002:SQK-LSK109",
                                protocol_run_id     = "f8320272-62ba-4f8d-821a-fb3dffcde338",
                                acquisition_run_id  = "564d52535b8db9cd5a084b612eed13cc68eaf349",
                                started             = datetime(2022, 3, 2, 13, 21, 2, 322037, tzinfo=tzutc()),
                                acquisition_stopped = datetime(2022, 3, 3, 14, 53, 9, 611224, tzinfo=tzutc()),
                                processing_stopped  = datetime(2022, 3, 3, 14, 53, 14, 662014, tzinfo=tzutc()),
                                basecalling_enabled = True,
                                sequencing_summary_file   = "sequencing_summary_PAK00383_564d5253.txt",
                                fast5_files_in_final_dest = 3126,
                                fast5_files_in_fallback   = 0,
                                fastq_files_in_final_dest = 3125,
                                fastq_files_in_fallback   = 0,
                                is_rna              = False,
                                run_time            = "26 hours" ) )

    def test_load_final_summary_rna(self):
        # Just to make sure I can spot and RNA cell
        example_file = os.path.join(DATA_DIR, "final_summary_PAK01185_f579772a.txt")

        fs = load_final_summary(example_file)
        self.assertEqual(fs['is_rna'], True)

    def test_load_final_summary_more(self):
        # I keep tweaking this function. I added a yamlfile option and the ability
        # to load the one file in a directory. Test this.
        example_dir = os.path.join(DATA_DIR, "fs") + "/"

        fs = load_final_summary(example_dir)
        self.assertEqual(fs['flow_cell_id'], "EXAMPLE_FS")

        fs2 = load_final_summary(example_dir,
                                 yamlfile = os.path.join(example_dir, "final_summary.yaml"))
        self.assertEqual(fs2['flow_cell_id'], "YAML_FS")

    def test_abspath(self):

        self.assertEqual( abspath('/tmp', relative_to='/proc'), '/tmp')

        self.assertEqual( abspath('null', relative_to='/dev/random'), '/dev/null')

    def test_groupby(self):

        fruits = "apple apricot durian cherry banana ambarella blueberry bilberry".split()

        self.assertEqual( dict(groupby(fruits, lambda f: f[0], sort_by_key=False)),
                          dict( a = ['apple', 'apricot', 'ambarella'],
                                d = ['durian'],
                                c = ['cherry'],
                                b = ['banana', 'blueberry', 'bilberry'] ) )
        # Since dict comparison does not consider order, check this explicitly:
        self.assertEqual( list(groupby(fruits, lambda f: f[0], sort_by_key=False)),
                          list("adcb") )

        self.assertEqual( dict(groupby(fruits, lambda f: f[0])),
                          dict( a = ['apple', 'apricot', 'ambarella'],
                                b = ['banana', 'blueberry', 'bilberry'],
                                c = ['cherry'],
                                d = ['durian'] ))
        self.assertEqual( list(groupby(fruits, lambda f: f[0])),
                          list("abcd") )

        # A function that forces the keys to sort as 'badc'.
        def some_sort_func(l):
            return dict((v,k) for k,v in enumerate("badc"))[l]

        self.assertEqual( list(groupby(fruits, lambda f: f[0], sort_by_key=some_sort_func)),
                          list("badc") )

    def test_od_key_replace(self):
        """Test this function which modifies dictionaries in-place
        """
        dict1 = OrderedDict([ ( 'apple', 1 ),
                              ( 'banana', 2 ),
                              ( 'blueberry', 3 ),
                              ( 'cherry', 4 ) ])

        self.assertFalse( od_key_replace(dict1, 'plum', 'prune') )
        self.assertTrue( od_key_replace(dict1, 'banana', 'xbanana') )
        self.assertTrue( od_key_replace(dict1, 'cherry', 'xcherry') )
        self.assertTrue( od_key_replace(dict1, 'apple', 'xapple') )

        # After those moves, we should have this result...
        self.assertEqual( dict1, OrderedDict([ ( 'xapple', 1 ),
                                               ( 'xbanana', 2 ),
                                               ( 'blueberry', 3 ),
                                               ( 'xcherry', 4 ) ]) )

    def test_glob(self):
        # Sort order in glob() results is important for consistency, but the numbered files produced
        # in fastq_pass and fast5_pass are like:
        #   fastq_pass/PAK01183_pass_bda16547_0.fastq.gz
        #   fastq_pass/PAK01183_pass_bda16547_1.fastq.gz
        #   fastq_pass/PAK01183_pass_bda16547_10.fastq.gz
        #   fastq_pass/PAK01183_pass_bda16547_100.fastq.gz
        # So we need a numeric order sort to keep them in proper order.
        glob_test_dir = os.path.join(DATA_DIR, "glob_test")
        assert os.path.exists(glob_test_dir)

        self.assertEqual( glob(glob_test_dir + "/*.dat"),
                          [ glob_test_dir + "/AAA.dat",
                            glob_test_dir + "/xxx.dat" ] )

        self.assertEqual( [ os.path.basename(f) for f in  glob(glob_test_dir + "/*.fastq.gz") ],
                          """PAK01183_fail_bda16547_0.fastq.gz
                             PAK01183_fail_bda16547_5.fastq.gz
                             PAK01183_fail_bda16547_10.fastq.gz
                             PAK01183_fail_bda16547_100.fastq.gz
                             PAK01183_fail_bda16547_101.fastq.gz
                             PAK01183_pass_bda16547_0.fastq.gz
                             PAK01183_pass_bda16547_5.fastq.gz
                             PAK01183_pass_bda16547_14.fastq.gz
                             PAK01183_pass_bda16547_20.fastq.gz
                             PAK01183_pass_bda16547_69.fastq.gz
                             PAK01183_pass_bda16547_100.fastq.gz
                             PAK01183_pass_bda16547_701.fastq.gz
                          """.split() )

        self.assertEqual( [ os.path.basename(f) for f in  glob(glob_test_dir + "/*") ],
                          """AAA.dat
                             PAK01183_fail_bda16547_0.fastq.gz
                             PAK01183_fail_bda16547_5.fastq.gz
                             PAK01183_fail_bda16547_10.fastq.gz
                             PAK01183_fail_bda16547_100.fastq.gz
                             PAK01183_fail_bda16547_101.fastq.gz
                             PAK01183_pass_bda16547_0.fastq.gz
                             PAK01183_pass_bda16547_5.fastq.gz
                             PAK01183_pass_bda16547_14.fastq.gz
                             PAK01183_pass_bda16547_20.fastq.gz
                             PAK01183_pass_bda16547_69.fastq.gz
                             PAK01183_pass_bda16547_100.fastq.gz
                             PAK01183_pass_bda16547_701.fastq.gz
                             xxx.dat
                          """.split() )

    def test_find_sequencing_summary(self):
        # Moved from the Snakefile
        run_dir = os.path.join(DATA_DIR, "runs/20210520_EGS1_16031BA")
        cell = "16031BApool01/20210520_1105_2-E1-H1_PAG23119_76e7e00f"
        self.assertEqual( find_sequencing_summary( run_dir, cell ),
                          run_dir + "/" + cell + "/sequencing_summary_PAG23119_0eaeb70c.txt" )

        # find_summary() should do the same thing (without backwards compatibility)
        self.assertEqual( find_summary("sequencing_summary.txt", run_dir, cell ),
                          run_dir + "/" + cell + "/sequencing_summary_PAG23119_0eaeb70c.txt" )

    def test_load_yaml(self):
        """Not much room for error here but still, always test.
        """
        # Relative load
        res1 = load_yaml("fs/final_summary.yaml", relative_to = DATA_DIR + "/fs")

        self.assertEqual(type(res1), OrderedDict)
        self.assertEqual(len(res1), 18)

    def test_dump_yaml(self):
        """YAML dumper now uses the blockquote style for multi-line strings which makes it
           easier to read, should you eve need to.
        """
        some_struct = dict( foo = [ "string one",
                                    "string\ntwo",
                                    "string\nthree\nhas\ttab\tcharacters\t" ] )

        dumped_yaml = dump_yaml(some_struct)

        self.assertEqual( dumped_yaml,
                          dd('''\
                                foo:
                                - string one
                                - |-
                                  string
                                  two
                                - "string\\nthree\\nhas\\ttab\\tcharacters\\t"
                             ''') )

    def test_empty_sc_data(self):
        """This just returns the same structure each time
        """
        self.assertEqual( type(empty_sc_data()), dict )
        self.assertEqual( len(empty_sc_data()), 7 )

if __name__ == '__main__':
    unittest.main()
