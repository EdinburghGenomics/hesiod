#!/usr/bin/env python3

"""Test the script that classifies experiments by name pattern"""

import sys, os, re
import unittest
import logging

from classify_expt import classify

class T(unittest.TestCase):

    def test_basic(self):
        """This function is very easy to test.
        """
        self.assertEqual(classify(""), dict(type="unknown"))

        self.assertEqual(classify("bad_expt_name"), dict(type="unknown"))

        # Assume that arbitrary names are test runs
        self.assertEqual(classify("00000000_XXX1_foo"), dict(type="test"))

        # Stuff starting with a number is internal
        self.assertEqual(classify("00000000_XXX1_123_blah_blah"), dict(type="internal"))

    def test_visitor(self):

        self.assertEqual( classify("00000000_XXX1_v_tbooth2_blah_blah"),
                          dict(type="visitor", uun="tbooth2") )

        # We're forgiving on punctuation
        self.assertEqual( classify("00000000_XXX1_V--TBooth2-blah_blah"),
                          dict(type="visitor", uun="tbooth2") )

        # This one is not good though
        self.assertEqual( classify("00000000_XXX1_v_tbooth2@example.com_blah_blah"),
                          dict(type="test") )

if __name__ == '__main__':
    unittest.main()
