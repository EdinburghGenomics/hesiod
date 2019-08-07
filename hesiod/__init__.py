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

    return res

# YAML convenience functions that use the ordered loader/saver
# yamlloader is basically the same as my yaml_ordered hack. It will go away with Py3.7.
def load_yaml(filename):
    """Load YAML from a file (not a file handle)."""
    with open(filename) as yfh:
        return yaml.load(yfh, Loader=yamlloader.ordereddict.CSafeLoader)

def dump_yaml(foo, filename=None):
    """Return YAML string or dump to a file (not a file handle)."""
    if filename:
        with open(filename, 'w') as yfh:
            return yaml.dump(foo, yfh, Dumper=yamlloader.ordereddict.CSafeDumper)
    else:
        return yaml.dump(foo, Dumper=yamlloader.ordereddict.CSafeDumper)
