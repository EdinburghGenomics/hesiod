# Common functions for testing
import re
from unittest.mock import mock_open, DEFAULT

def jstr(instr):
    """Justify a string. Makes the tests neater.
    """
    # Hmm - I wrote this recently but can't for the life of me remember where it was.
    # So I write it again.
    # Oh - and now I realise I should have used textwrap.dedent. Oh well, I'll fix
    # it at some point.

    if "\n" not in instr:
        return instr

    str_lines = instr.split("\n")

    # Number of spaces after final "\n" gives indent,
    if re.match("^ *$", str_lines[-1]):
        indent = len(str_lines[-1]) + 3
        for n in range(1, len(str_lines)):
            str_lines[n] = re.sub(f"^ {{{indent}}}", "", str_lines[n])
        str_lines[-1] = ''

    return "\n".join(str_lines)


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

