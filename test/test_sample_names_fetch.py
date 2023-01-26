#!/usr/bin/env python3

"""Test the code that fetches the sample names file"""

import sys, os, re
import unittest
import logging

DATA_DIR = os.path.abspath(os.path.dirname(__file__) + '/examples/sample_names_txt')
VERBOSE = os.environ.get('VERBOSE', '0') != '0'

from sample_names_fetch import find_tsv, parse_tsv

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

    def tearDown(self):
        pass

    ### THE TESTS ###
    def test_find_tsv(self):

        # Explicit to this pool
        res1 = find_tsv( experiment = '20220101_EGS2_12345XX',
                         cell = '12345XXpool01/20220101_1142_1E_PAM30735_b8d4bc73',
                         dir = DATA_DIR )
        self.assertEqual(res1, f"{DATA_DIR}/12345XXpool01_sample_names.tsv")

        # Explicit to this flowcell ID
        res2 = find_tsv( experiment = '20220101_EGS2_12345XX',
                         cell = '12345XXpool02/20220101_1142_1E_PAM30735_b8d4bc73',
                         dir = DATA_DIR )
        self.assertEqual(res2, f"{DATA_DIR}/PAM30735_sample_names.tsv")

        # Explicit to this flowcell ID in a subdir
        res3 = find_tsv( experiment = '20220101_EGS2_12345XX',
                         cell = '12345XXpool02/20220101_1142_1E_PAM76543_b8d4bc73',
                         dir = DATA_DIR )
        self.assertEqual(res3, f"{DATA_DIR}/subdir/PAM76543_sample_names.tsv")

        # Default for this project
        res4 = find_tsv( experiment = '20220101_EGS2_12345XX',
                         cell = '12345XXpool02/20220101_1142_1E_PAM76599_b8d4bc73',
                         dir = DATA_DIR )
        self.assertEqual(res4, f"{DATA_DIR}/12345_sample_names.tsv")

        # Nothing found
        res4 = find_tsv( experiment = '20220101_EGS2_12346XX',
                         cell = '12346XXpool02/20220101_1142_1E_PAM76599_b8d4bc73',
                         dir = DATA_DIR )
        self.assertEqual(res4, None)


    def test_parse_tsv_good(self):

        # Full example, well behaved
        res1 = parse_tsv(f"{DATA_DIR}/12345_sample_names.tsv")

        self.assertEqual( res1, dict( barcodes =
                              [ { 'bc': 'barcode01',
                                  'int_name': '12345XX0001',
                                  'ext_name': 'Sample number one' },
                                { 'bc': 'barcode02',
                                  'int_name': '12345XX0002',
                                  'ext_name': 'Sample number two' },
                                { 'bc': 'barcode03',
                                  'int_name': '12345XX0003',
                                  'ext_name': 'Sample number three' },
                                { 'bc': 'barcode04',
                                  'int_name': '12345XX0004',
                                  'ext_name': 'Sample number four' },
                                { 'bc': 'barcode12',
                                  'int_name': '12345XX0005',
                                  'ext_name': 'Another lovely sample' } ] ) )


        # Full example, janky but ok
        res2 = parse_tsv(f"{DATA_DIR}/12345XXpool01_sample_names.tsv")

        self.assertEqual( res2, dict( barcodes =
                              [ { 'bc': 'barcode01',
                                  'int_name': '12345XX0001',
                                  'ext_name': '12345XX0001' },
                                { 'bc': 'barcode02',
                                  'int_name': '12345XX0002',
                                  'ext_name': '12345XX0002' },
                                { 'bc': 'barcode03',
                                  'int_name': '12345XX0003',
                                  'ext_name': 'Sample number three' },
                                { 'bc': 'barcode04',
                                  'int_name': '12345XX0004',
                                  'ext_name': 'Another lovely  sample' },
                                { 'bc': 'barcode12',
                                  'int_name': '12345XX0005',
                                  'ext_name': 'Another lovely  sample' } ] ) )


    def test_parse_tsv_bad(self):

        # Repeated int_name
        res1 = parse_tsv(f"{DATA_DIR}/PAM30734_sample_names.tsv")
        self.assertEqual( res1, dict( error = "Repeated internal name 12345XX0022" ) )

        # Repeated barcode
        res2 = parse_tsv(f"{DATA_DIR}/PAM30735_sample_names.tsv")
        self.assertEqual( res2, dict( error = "Repeated barcode barcode02" ) )

        # Missing int_name
        res3 = parse_tsv(f"{DATA_DIR}/PAM30736_sample_names.tsv")
        self.assertEqual( res3, dict( error = "Missing internal name for barcode03" ) )

        # Un-parseable line at end of file
        res4 = parse_tsv(f"{DATA_DIR}/PAM30737_sample_names.tsv")
        self.assertEqual( res4, dict( error = "Unable to parse line 7" ) )

if __name__ == '__main__':
    unittest.main()
