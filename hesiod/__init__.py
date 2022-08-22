#!/usr/bin/env python3
import os, re
from collections import OrderedDict
import yaml, yamlloader

# For parsing of ISO/RFC format dates (note that newer Python has datetime.datetime.fromisoformat
# but we're using dateutil.parser.isoparse from python-dateutil 2.8)
from dateutil.parser import isoparse
from datetime import timedelta
from collections import namedtuple

def glob():
    """Regular glob() is useful but we want consistent sort order, including
       for the numbnered files produced by the Promethion.
    """
    from glob import glob

    key_regex = re.compile(r"(?<=[._])(\d+)(?=[._])")
    def key_func(filename):
        r"""Strategy is that if we see /_\d+\./ then zero-pad the number to 8 chars so
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
    # FIXME - there are PyPi modules that do this.
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

def parse_cell_name(experiment, cell):
    """Things we get from parsing wildcards.cell
    """
    # Some sanity checks
    if experiment.count('/') != 0 or cell.count('/') != 1:
        raise ValueError(f"Unexpected number of '/' in parse_cell_name({experiment!r}, {cell!r})")

    res = OrderedDict()
    res['Experiment'] = experiment
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
    res['Base'] = "{Cell}/{Experiment}_{Library}_{CellID}_{Checksum}".format(**res)

    return res

def load_final_summary(filename, yamlfile=None):
    """Load the info from a final_summary file. Why could they not use YAML or JSON for these??
    """
    # If yaml is supplied and exists, read this in preference to the text file
    if yamlfile and os.path.exists(yamlfile):
        return load_yaml(yamlfile)

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

    # Normally we can't predict the exact filename, so allow just specifying the directory.
    try:
        if filename.endswith('/'):
            filename, = glob(filename + "final_summary_*_*.txt")
    except ValueError:
        raise RuntimeError("Bad glob match for {!r}".format(filename + "final_summary_*_*.txt"))

    # Easy txt-to-dict loader
    with open(filename) as fh:
        res = dict([aline.rstrip("\n").split("=", 1) for aline in fh ])

    # Coerce the data types to the target types
    for k in list(res):
        res[k] = data_types.get(k, str)(res[k])

    # See if we think this is RNA
    res['is_rna'] = 'RNA' in res['protocol']

    # Put the run time into hours
    try:
        td = res['acquisition_stopped'] - res['started']
        td_hours = round(td / timedelta(hours=1))
        if td_hours >= 2:
            res['run_time'] = f"{td_hours} hours"
        else:
            td_minutes = round(td / timedelta(minutes=1))
            res['run_time'] = f"{td_minutes} minutes"
    except KeyError:
        res['run_time'] = "unknown"

    return res

def find_sequencing_summary(rundir, cell):
    """For a given cell, the sequencing summary may be in the top level dir (new style) or in a
       sequencing_summary subdirectory (old style). From MinKNOW 3.6+ the naming convention changes
       too.
       In any case there should be only one.
    """
    found = glob(f"{rundir}/{cell}/*_sequencing_summary.txt") + \
            glob(f"{rundir}/{cell}/sequencing_summary/*_sequencing_summary.txt") + \
            glob(f"{rundir}/{cell}/sequencing_summary_*_*.txt")

    assert len(found) == 1, ( "There should be exactly one sequencing_summary.txt per cell"
                              f" - found {len(found)}." )

    return found[0]

def fast5_out(f5_in):
    """Given an input .fast5 file in the expdir, say what the output .fast5 will be
    """
    f5_split = f5_in.split('/')
    pf = f5_split[2].split('_')[1]

    if len(f5_split) == 5:
        # has barcode
        return f"{f5_split[0]}/{f5_split[1]}/fast5_{f5_split[3]}_{pf}/{f5_split[-1]}"
    else:
        return f"{f5_split[0]}/{f5_split[1]}/fast5_._{pf}/{f5_split[-1]}"

def find_summary(pattern, rundir, cell, allow_missing=False):
    """Find other summary files. For the newer runs, this could replace find_sequencing_summary()
    """
    prefix, suffix = pattern.split('.')

    found = glob(f"{rundir}/{cell}/{prefix}_*_*.{suffix}")

    if allow_missing and not found:
        return None

    assert len(found) == 1, f"Found {len(found)} {pattern} for cell {cell}"
    return found[0]

# YAML convenience functions that use the ordered loader/saver
# yamlloader is basically the same as my yaml_ordered hack. It will go away with Py3.7.
def load_yaml(filename, relative_to=None, as_tuple=None):
    """Load YAML from a file (not a file handle).
       If specified, relative paths are resolved relative to os.path.dirname(relative_to)
    """
    with open(abspath(filename, relative_to)) as yfh:
        res = yaml.load(yfh, Loader=yamlloader.ordereddict.CSafeLoader)

    if not as_tuple:
        return res

    else:
        # This is just to make the syntax a little cleaner in the Snakefile
        return namedtuple(as_tuple, res)(**res)

def empty_sc_data():
    """Return an empty data structure in the same format as scan_cells.py
    """
    res = dict( cells_per_lib = {},
                cells_per_project = {},
                counts = dict( cells = 0,
                               cellsaborted = 0,
                               cellsready = 0 ),
                printable_counts = "[EMPTY_SC_DATA]",
                representative_fast5 = None,
                scanned_cells = {} )

    return namedtuple("empty_sc_data", res)(**res)

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
