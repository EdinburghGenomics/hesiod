#!/usr/bin/env python3

"""Test the functions in test/__init__.py"""

import sys, os, re
import unittest

from . import jstr

class T(unittest.TestCase):

    def test_jstr(self):

        # Seems I didn't know about "textwrap.dedent" when I made this function, but
        # mine is slightly different so I'll keep it for now.
        self.assertEqual(jstr(""), "")

        self.assertEqual(jstr(
            """Here is a
               string that has
                 been indented

               into the code.
            """),
            "Here is a\nstring that has\n  been indented\n\ninto the code.\n")

        self.assertEqual(jstr(
            """Not a
               justifiable
string"""),
            "Not a\n               justifiable\nstring")

if __name__ == '__main__':
    unittest.main()
