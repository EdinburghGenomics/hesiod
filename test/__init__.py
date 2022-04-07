# Common functions for testing
import re
from unittest.mock import mock_open, DEFAULT

def fp_mock_open(filepattern='.*', **kwargs):
    """A version of the standard mock_open that only mocks when filepattern
       matches the given pattern.
    """
    mo_obj = mock_open(**kwargs)
    filepattern = filepattern.rstrip("$") + '$'

    # capture open() in a closure now before any patching can happen
    real_open = open

    def new_call(filename, *args, **kwargs):
        if not re.match(filepattern, filename):
            return real_open(filename, *args, **kwargs)
        else:
            return DEFAULT

    # Patch the mo_obj and return it
    mo_obj.side_effect = new_call
    return mo_obj

