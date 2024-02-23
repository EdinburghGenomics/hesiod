#!/usr/bin/env python3

"""Check reading the metadata from a FASTQ file"""

import sys, os, re
import unittest
import logging
from collections import OrderedDict

DATA_DIR = os.path.abspath(os.path.dirname(__file__) + '/examples')
VERBOSE = os.environ.get('VERBOSE', '0') != '0'

from get_fastq_metadata import md_from_header_line

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

    def test_header_empty(self):
        """Base case
        """
        header = "@empty"
        md = md_from_header_line(header)

        expected = dict( basecall_model = 'unknown' )

        self.assertEqual(type(md), OrderedDict)
        self.assertEqual(dict(md), expected)


    def test_header_convert(self):
        """I'll assume the other stuff in the script works. Just test the core.
        """
        header = ("@88078189-2577-42e4-974e-e868fd9bcce7 runid=5ed8849a0f6b8d388566af4955ce048a28f3fa09"
                  " read=5 ch=1153 start_time=2024-02-22T15:52:51.572584+00:00 flow_cell_id=PAS23464"
                  " protocol_group_id=Is_PromethION_Working sample_id=DoesThisWork"
                  " barcode=unclassified barcode_alias=unclassified"
                  " parent_read_id=88078189-2577-42e4-974e-e868fd9bcce7"
                  " basecall_model_version_id=dna_r10.4.1_e8.2_400bps_sup@v4.2.0")
        md = md_from_header_line(header)

        # This is identical to the FAST5 aside from the file version tag.
        expected = dict( runid          = "5ed8849a0f6b8d388566af4955ce048a28f3fa09",
                         flowcell       = "PAS23464",
                         experiment     = "Is_PromethION_Working",
                         sample         = "DoesThisWork",
                         barcode        = "unclassified",
                         basecall_model = "dna_r10.4.1_e8.2_400bps_sup@v4.2.0" )

        self.assertEqual(dict(md), expected)

if __name__ == '__main__':
    unittest.main()
