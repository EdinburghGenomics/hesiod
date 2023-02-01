"""Useful functions for data structure manipulation.
"""
from collections import OrderedDict

def od_key_replace(odict, oldkey, newkey):
    """Changes the key in an OrderedDict to a new key,
       preserving the order. There is no particularly efficient way
       to do this but we assume the dict is fairly small.
       Returns True if the replacement was made, False otherwise
    """
    if oldkey not in odict:
        # Check this first - maybe the key was already renamed and
        # that's OK.
        return False

    if newkey in odict:
        # Disallow overwriting
        raise KeyError(f"{newkey!r} is already in the dictionary")

    # The only re-ordering tool we have is move_to_end() but we can
    # make do with that.
    odict[newkey] = odict[oldkey]

    push_flag = False
    for k in list(odict.keys()):
        if k == oldkey:
            push_flag = True
            del odict[k]
        elif k == newkey:
            pass
        elif push_flag:
            odict.move_to_end(k)

    return True

# Another generic and useful function...
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
