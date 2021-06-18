#!/bin/env python3

import gzip
import tempfile
from io import BytesIO
import shutil
import logging
import timeit

import h5py
from tqdm import tqdm

# Reading directly from fast5.gz is a bad idea as it's super-slow.
# This version decompresses into /dev/shm and cleans up nicely.

# An accumulator
class MinMax:
    def __init__(self):
        self.min = None
        self.max = None

    def add(self, v):
        if self.min is None:
            self.min = self.max = v
        elif v < self.min:
            self.min = v
        elif v > self.max:
            self.max = v

    def __repr__(self):
        if not self.min:
            return "No values"
        elif self.min == self.max:
            return "{}".format(self.min)
        else:
            return "{}-{}".format(self.min, self.max)


def read_fast5(fh):
    starts = MinMax()
    durations = MinMax()

    with tqdm() as pbar:
        with h5py.File(fh, 'r') as handle:

            # Version check!? In development the files are '1.0'
            # so maybe I should check for this?
            try:
                assert handle.attrs['file_version'] == b'1.0'
            except Exception:
                logging.exception("Version check failed")

            # We need all the items matching Raw/Reads/{}. In the sample code we get
            # for read in handle['Raw/Reads'].keys():
            #   read_group = handle['Raw/Reads/{}'.format(read)]

            # But I think we can just do this?
            for n, v in enumerate(handle.values()):
                attrs = v['Raw'].attrs

                # Note that the more attributes you actually read from the file the longer
                # it takes. Casting attrs to a dict (ie readign all values) triples the read time.
                starts.add(attrs['start_time'])
                durations.add(attrs['duration'])

                pbar.update()

    print("Extracted {} attrs from file ; start_time {} ; duration {}.".format(n+1, starts, durations))

# Now the tests.
### With a temp file (fast)

with tempfile.TemporaryFile(dir='/dev/shm', suffix='.fast5' ) as tfh:
    with gzip.open('big.fast5.gz', 'rb') as zfh:
        shutil.copyfileobj(zfh, tfh)
    tfh.seek(0)

    print(timeit.timeit('read_fast5(tfh)', globals=globals(), number=4))

### With a memory buffer (faster!)
with BytesIO() as tfh2:
    with gzip.open('big.fast5.gz', 'rb') as zfh:
        shutil.copyfileobj(zfh, tfh2)
    tfh2.seek(0)

    print(timeit.timeit('read_fast5(tfh2)', globals=globals(), number=4))

### With nothing (this takes about half an hour!)
"""
with gzip.open('big.fast5.gz', 'rb') as zfh:

    print(timeit.timeit('read_fast5(zfh)', globals=globals(), number=4))
"""
