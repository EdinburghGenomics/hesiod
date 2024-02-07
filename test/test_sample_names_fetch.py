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
    def test_find_tsv_good(self):

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

    def test_find_tsv_bad(self):

        # Nothing found
        res4 = find_tsv( experiment = '20220101_EGS2_12346XX',
                         cell = '12346XXpool02/20220101_1142_1E_PAM76599_b8d4bc73',
                         dir = DATA_DIR )
        self.assertEqual(res4, None)

        # Bad data dir
        res5 = find_tsv( experiment = '20220101_EGS2_12345XX',
                         cell = '12345XXpool01/20220101_1142_1E_PAM30735_b8d4bc73',
                         dir = '/dev/null/nosuchfile' )
        self.assertEqual(res5, None)

        # Unparseable cell name
        with self.assertRaises(ValueError):
            res6 = find_tsv( experiment = 'woo',
                             cell = 'woo' )

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
                                  'ext_name': None },
                                { 'bc': 'barcode02',
                                  'int_name': '12345XX0002',
                                  'ext_name': None },
                                { 'bc': 'barcode03',
                                  'int_name': '12345XX0003',
                                  'ext_name': 'Sample number three' },
                                { 'bc': 'barcode04',
                                  'int_name': '12345XX0004',
                                  'ext_name': 'Another lovely sample' },
                                { 'bc': 'barcode12',
                                  'int_name': '12345XX0005',
                                  'ext_name': 'Another lovely  sample' } ] ) )

    def test_parse_csv_again(self):
        """This example did not parse and I could not immediately see why.
           In fact, I'd written "barocde11" instead of "barcode11", so the failure
           is legit. But I've decided to make the code more tolerant and make it
           work!
        """
        res = parse_tsv(f"{DATA_DIR}/29490_sample_names.tsv")

        self.assertEqual( res, dict( barcodes =
                              [ { 'bc': "barcode11",
                                  'int_name': "29490KG0001L01",
                                  'ext_name': "RNA1" },
                                { 'bc': "barcode12",
                                  'int_name': "29490KG0002L01",
                                  'ext_name': "RNA2" },
                                { 'bc': "barcode13",
                                  'int_name': "29490KG0003L01",
                                  'ext_name': "RNA3" } ] ) )

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
        self.assertEqual( res4, dict( error = "Unable to parse barcode on line 7" ) )

        # Empty file
        res5 = parse_tsv("/dev/null")
        self.assertEqual( res5, dict( error = "No barcodes found in the file" ) )

        # Unreadable file
        res6 = parse_tsv("/dev/null/nosuchfile")
        self.assertEqual( res6, dict( error = "[Errno 20] Not a directory: '/dev/null/nosuchfile'" ) )


if __name__ == '__main__':
    unittest.main()
