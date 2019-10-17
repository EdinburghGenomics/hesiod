#!/usr/bin/env python3
import os, re
from collections import OrderedDict
import yaml, yamlloader

# Some utility functions/constants for use in Hesiod.
hesiod_version = 'unknown'

try:
    with open(os.path.dirname(__file__) + '/../version.txt') as fh:
        hesiod_version = fh.read().strip()
except OSError:
    pass

def glob():
    """Regular glob() is useful but we want consistent sort order."""
    from glob import glob
    return lambda p: sorted( (f.rstrip('/') for f in glob(os.path.expanduser(p))) )
glob = glob()

def parse_cell_name(cell):
    """Things we get from parsing wildcards.cell"""
    res = OrderedDict()
    res['Cell'] = cell

    # Now shred the filename.
    mo = re.match(r'([^/]+)/(\d{8})_(\d+)_([0-9A-Z-]+)_([0-9A-Z]+)_([0-9a-f]{8})$', cell)
    if mo:
        for n, x in enumerate("Library Date Number Slot CellID Checksum".split()):
            res[x] = mo.group(n+1)
    else:
        # Not good, but we'll try
        res['Library'] = cell.split('/')[0]
        res['CellID'] = cell.split('_')[-2] if '_' in cell else 'UNKNOWN'

    # FIXME - not sure this is the right thing to do when the regex fails.
    mo =  re.match(r"([0-9]{5})[A-Z]{2}", res['Library'])
    if mo:
        res['Project'] = mo.group(1)
    else:
        res['Project'] = res['Library']

    return res

# YAML convenience functions that use the ordered loader/saver
# yamlloader is basically the same as my yaml_ordered hack. It will go away with Py3.7.
def load_yaml(filename):
    """Load YAML from a file (not a file handle)."""
    with open(filename) as yfh:
        return yaml.load(yfh, Loader=yamlloader.ordereddict.CSafeLoader)

def dump_yaml(foo, filename=None):
    """Return YAML string and optionally dump to a file (not a file handle)."""
    ydoc = yaml.dump(foo, Dumper=yamlloader.ordereddict.CSafeDumper)
    if filename:
        with open(filename, 'w') as yfh:
            print(ydoc, file=yfh, end='')
    return ydoc

# Another generic and useful function
def groupby(iterable, keyfunc, sort_by_key=True):
    """A bit like itertools.groupby() but returns a dict (or rather an OrderedDict)
       of lists, rather than an iterable of iterables.
       There is no need for the input list to be sorted.
       If sort_by_key is False the order of the returned dict will be in the order
       that keys are seen in the iterable.
       If sort_by_key is callable then the order of the returned dict will be sorted
       by this key function, else it will be sorted in the default ordering. Yeah.
       The lists themselves will always be in the order of the original iterable.
    """
    res = OrderedDict()
    for i in iterable:
        res.setdefault(keyfunc(i), list()).append(i)

    if not sort_by_key:
        return res
    elif sort_by_key is True:
        return OrderedDict(sorted(res.items()))
    else:
        return OrderedDict(sorted(res.items(), key=lambda t: sort_by_key(t[0])))

def slurp_file(filename):
    """Standard file slurper. Returns a list of lines.
    """
    with open(filename) as fh:
        return [ l.rstrip("\n") for l in fh ]

