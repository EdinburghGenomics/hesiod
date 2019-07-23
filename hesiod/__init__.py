#!/usr/bin/env python3
import os

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
    res['Run'] = RUN
    res['Cell'] = cell

    # Now shred the filename.
    mo = re.match(r'([0-9A-Z-]+)/(\d{8})_(\d+)_([0-9A-Z-]+)_([0-9A-Z]+)_([0-9a-f]{8})$', cell)
    if mo:
        for n, x in enumerate("Library Date Number Slot CellID Checksum".split()):
            res[x] = mo.group(n+1)
    else:
        # Not good, but we'll try
        res['Library'] = cell.split('/')[0]
        res['CellID'] = cell.split('_')[-2] if '_' in cell else 'UNKNOWN'

    return res
