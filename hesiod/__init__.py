#!/usr/bin/env python3
import os, re
from collections import OrderedDict
import yaml, yamlloader

# For parsing of ISO/RFC format dates (note that newer Python has datetime.datetime.fromisoformat
# but we're using dateutil.parser.isoparse from python-dateutil 2.8)
from dateutil.parser import isoparse

def glob():
    """Regular glob() is useful but we want consistent sort order, including
       for the numbnered files produced by the Promethion.
    """
    from glob import glob

    key_regex = re.compile(r"(?<=[._])(\d+)(?=[._])")
    def key_func(filename):
        """Strategy is that if we see /_\d+\./ then zero-pad the number to 8 chars so
           that dictionary sort will produce a numeric sort.
        """
        return re.sub(key_regex, lambda d: d.group().rjust(8,'0'), filename)

    return lambda p: sorted( (f.rstrip('/') for f in glob(os.path.expanduser(p))),
                             key = key_func )
glob = glob()

def _determine_version():
    """Report the version of Hesiod being used. Normally this is in version.txt
       but we can factor in GIT commits in the dev environment.
       Note that uncommitted code cannot easily be detected so I don't try.
    """
    try:
        with open(os.path.dirname(__file__) + '/../version.txt') as fh:
            vers = fh.read().strip()
    except OSError:
        return 'unknown'

    # Inspired by MultiQC, if there is a .git dir then dig into it
    try:
        with open(os.path.dirname(__file__) + '/../.git/HEAD') as fh:
            git_head = fh.read().strip()

        if git_head.startswith('ref:'):
            # We're at a branch tip
            git_branch = git_head[5:]
            git_branch_name = git_branch.split('/')[-1]

            # Load the actual commit ID
            with open(os.path.dirname(__file__) + '/../.git/' + git_branch) as fh:
                git_head = fh.read().strip()
        else:
            git_branch_name = 'none'

        # Having done all that, see if git_head matches the tag that matches vers
        with open(os.path.dirname(__file__) + '/../.git/refs/tags/v' + vers) as fh:
            git_version_commit = fh.read().strip()

        if git_version_commit != git_head:
            # No it doesn't. So add some extra info to the version.
            vers = "{}-{}-{}".format(vers, git_branch_name, git_head[:8])

    except OSError:
        # We're not getting anything useful from .git
        pass

    return vers

def parse_cell_name(run, cell):
    """Things we get from parsing wildcards.cell
    """
    res = OrderedDict()
    res['Run'] = run
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
        res['Checksum'] = cell.split('_')[-1] if '_' in cell else 'UNKNOWN'

    # FIXME - not sure this is the right thing to do when the regex fails.
    mo =  re.match(r"([0-9]{5})[A-Z]{2}", res['Library'])
    if mo:
        res['Project'] = mo.group(1)
    else:
        res['Project'] = res['Library']

    # Given all this, what do we call output files releting to this cell?
    # See doc/naming_convention.txt
    res['Base'] = "{Cell}/{Run}_{Library}_{CellID}_{Checksum}".format(**res)

    return res

def load_final_summary(filename):
    """Load the info from a final_summary file. Why could they not use YAML or JSON for these??
    """
    def make_bool(x):
        return x[0] in "1TtYy"

    data_types = dict( fast5_files_in_final_dest = int,
                       fast5_files_in_fallback   = int,
                       fastq_files_in_final_dest = int,
                       fastq_files_in_fallback   = int,
                       basecalling_enabled       = make_bool,
                       started                   = isoparse,
                       acquisition_stopped       = isoparse,
                       processing_stopped        = isoparse, )

    # Easy txt-to-dict loader
    with open(filename) as fh:
        res = dict([aline.rstrip("\n").split("=", 1) for aline in fh ])

    # Coerce the data types to the target types
    for k in list(res):
        res[k] = data_types.get(k, str)(res[k])

    return res

# YAML convenience functions that use the ordered loader/saver
# yamlloader is basically the same as my yaml_ordered hack. It will go away with Py3.7.
def load_yaml(filename, relative_to=None):
    """Load YAML from a file (not a file handle).
       If specified, relative paths are resolved relative to os.path.basename(relative_to)
    """
    with open(abspath(filename)) as yfh:
        return yaml.load(yfh, Loader=yamlloader.ordereddict.CSafeLoader)

def abspath(filename, relative_to=None):
    """Version of abspath which can optionally be resolved relative to another file.
    """
    if relative_to and not filename.startswith('/'):
        return os.path.abspath(os.path.join(os.path.dirname(relative_to), filename))
    else:
        return os.path.abspath(filename)

def dump_yaml(foo, filename=None):
    """Return YAML string and optionally dump to a file (not a file handle)."""
    ydoc = yaml.dump(foo, Dumper=yamlloader.ordereddict.CSafeDumper, default_flow_style=False)
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

hesiod_version = _determine_version()
