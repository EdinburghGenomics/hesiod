#!/usr/bin/env python3

"""Using BioPython, get the longest N reads from a fastq[.gz] file.

   I may add alternative criteria in future.
"""

from Bio import SeqIO
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
import logging as L

from collections import deque

class TopResults:
    """A holder for the top N results. I could use cachetools here but I decided
       to roll my own.
    """
    def __init__(self, maxlen=1):
        self._res = deque(maxlen=maxlen)
        self._res_full = False

        # The measured score could be the sequence length, or any properly that is
        # comparable. After a while, most values chacked will be <=minval and we can
        # quickly ignore them, assuming that the values are not being added in order
        # of score.
        # I could make a special case for when maxlen=1 but given the assumption that
        # calling self._add() is relatively rare I don't think I'll bother. If the
        # input was ordered by ascending score and maxlen=1 then this would be worth
        # fixing.
        self._minscore = None

    def add(self, item, score):
        """Adds a new item with a given score.
           Item may be any object.
           Score may be anything that supports comparisons
        """
        # Is it worth having a flag for when the deque gets full? Probably
        # saves a few CPU cycles calling len().
        if self._res_full:
            if score > self._minscore:
                # Insert into the deque
                self._add(item, score)
                self._minscore = self._res[-1][0]
        else:
            # Always insert
            self._add(item, score)
            self._minscore = self._res[-1][0]

            # Then see if that filled up the deque yet.
            self._res_full = (len(self._res) == self._res.maxlen)

    def _add(self, item, score):
        """Adds a new item with a given score.
           This assumes that the item belongs in the deque and looks for
           a place to put it, which would be inefficient but .add() will skip
           most new items quickly by comparing to self._minscore.
        """
        # Let's do a binary search on the deque
        res = self._res
        #L.debug(f"Adding item with score {score!r} to deque of len {len(res)}")

        if len(res) == res.maxlen:
            #L.debug("Discarding lowest item in the deque")
            res.pop()

        search_top = 0
        search_bottom = len(res)

        while search_bottom > search_top:
            i = (search_bottom + search_top) // 2

            #L.debug(f"Searching at {search_top}-{i}-{search_bottom}")

            if score > res[i][0]:
                # Just while testing
                assert search_bottom != i
                search_bottom = i
            else:
                search_top = i + 1

        #L.debug(f"Inserting at {search_top}")
        res.insert(search_top, (score, item))

    def get_top(self):
        return [r[1] for r in self._res]

    def get_top_scored(self):
        return list(self._res)

def main(args):

    for record in SeqIO.parse("Quality/example.fastq", "fastq"):

        pass

def parse_args(*args):
    description = """Using BioPython, get the longest N reads from a fastq[.gz] file.
                  """

    argparser = ArgumentParser( description=description,
                                formatter_class = ArgumentDefaultsHelpFormatter )

    argparser.add_argument("-n", "--num_records", type=int, default=1,
                            help="Return the longest N reads.")
    argparser.add_argument("infiles", nargs='+',
                            help="Files to read from.")

    return argparser.parse_args(*args)

# Test tiem
def test_top_results():
    from random import randrange
    from pprint import pprint

    L.basicConfig(level = L.DEBUG)

    tr = TopResults(10)

    for n in range(100000):
        newval = randrange(0,1000)
        tr.add(f"{newval:02d}", newval)

    pprint(tr.get_top_scored())

if __name__ == "__main__":

    main(parse_args())
