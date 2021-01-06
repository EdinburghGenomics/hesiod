#!/usr/bin/env python3
import os, sys, re
import logging as L
import shutil
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from pprint import pformat, pprint

DRY_RUN = []
TALLIES = dict( runs = 0,
                fastqdirs = 0 )

# Could import this from hesiod/__init__.py but I don't want the deps.
def glob():
    """Regular glob() is useful but we want consistent sort order."""
    from glob import glob
    return lambda p: sorted( (f.rstrip('/') for f in glob(os.path.expanduser(p))) )
glob = glob()

def main(args):

    if args.debug:
        L.basicConfig( level = L.DEBUG,
                       format = "{levelname}: {message}",
                       style = '{' )
    else:
        L.basicConfig( level=L.INFO,
                       format = "{message}",
                       style = '{' )

    if args.no_act:
        DRY_RUN.append(True)

    try:
        args.func(args)
    except AttributeError:
        # Force a full help message
        parse_args(['--help'])

    for k, v in TALLIES.items():
        if v:
            L.info("Moved {} {}.".format(v, k))

def mv_main(args):
    """Move one or more runs to a given location.
    """
    # Validate the dest dir
    real_dest = os.path.realpath(args.to_dir)
    L.info("Moving to {}".format(real_dest))
    if not os.path.isdir(real_dest):
        L.error("No such directory {}".format(real_dest))
        return

    # Loop through the runs
    for arun in args.runs:

        run_name = os.path.basename(arun.rstrip('/'))
        dest_name = os.path.join(real_dest, run_name)

        # Is it already there?
        if os.path.exists(dest_name):
            L.error("There is already a directory {}".format(dest_name))
            continue

        # Am I trying to move the directory into itself? Actually I think Python
        # shutil.move catches this one for me. Yes it does.

        # See if this is a rundir or a fastqdir
        if not os.path.isdir(arun):
            L.error("No such directory {}".format(arun))
        elif is_rundir(arun):
            move_rundir(arun, dest_name)
        elif is_fastqdir(arun):
            move_fastqdir(arun, dest_name)
        else:
            L.error("Not a valid run dir or fastq dir {}".format(arun))

def is_rundir(somedir):
    """Run dirs have pipeline/output symlink.
    """
    return os.path.islink(os.path.join(somedir, 'pipeline', 'output'))

def is_fastqdir(somedir):
    """Fasqdata dirs have a rundata symlink.
    """
    return os.path.islink(os.path.join(somedir, 'rundata'))

def move_rundir(arun, dest_name):
    """Given a run and a destination, move it.
       The pipeline/output and pipeline/output/rundata symlinks will be fixed.
    """
    # This should be already done by the caller. Doing it here is problematic for
    # dry runs where the directory may in fact not exist!
    #dest_name = os.path.realpath(dest_name)

    # Read the pipeline/output symlink. This may be a relative link so we always
    # convert it to an absolute link by putting it through os.path.realpath()
    output_link = os.path.join(arun, 'pipeline', 'output')
    output_link_dest = os.readlink(output_link)
    output_link_abs = os.path.realpath(output_link)

    if not os.path.isdir(output_link_abs):
        # The link is broken. So we'll not touch it.
        L.warning("{} link is invalid. Will not modify links.".format(output_link))
        output_link_abs = None
    else:
        # rundata_link needs to be the real path of the link (as opposed to the real path of
        # where the link points!)
        rundata_link = os.path.join(output_link_abs, 'rundata')
        rundata_link_dest = os.readlink(rundata_link)
        rundata_link_abs = os.path.realpath(rundata_link)

        # Now the rundata_link should point back to arun or we're in trouble!
        if not rundata_link_abs == os.path.realpath(arun):
            L.error("{} link does not point back to {}".format(rundata_link, arun))
            return

    # OK we're ready to move the run
    L.info("shutil.move({!r}, {!r})".format(arun, dest_name))
    if not DRY_RUN:
        shutil.move(arun, dest_name)
    # And this changes where the output link is
    output_link = os.path.join(dest_name, 'pipeline', 'output')

    if output_link_abs and output_link_abs != output_link_dest:
        L.warning("Converting pipeline/output link to an absolute path")
        L.info("os.symlink({!r}, {!r})".format(output_link_abs, output_link))
        if not DRY_RUN:
            os.unlink(output_link)
            os.symlink(output_link_abs, output_link)

    # And finally, rundata_link must change unless output_link was dangling.
    if output_link_abs:
        L.info("os.symlink({!r}, {!r})".format(dest_name, rundata_link))
        if not DRY_RUN:
            os.unlink(rundata_link)
            os.symlink(dest_name, rundata_link)

    L.info("Renamed {} to {}{}".format(arun, dest_name, " [DRY_RUN]" if DRY_RUN else ""))
    TALLIES['runs'] += 1

# Note - I could abstract this function and avoid copy-paste but it would be a lot less legible.
def move_fastqdir(afqd, dest_name):
    """Given a fastqdata directory and a destination, move it.
       The rundata/pipeline/output and rundata symlinks will be fixed.
    """
    # This should be already done by the caller.
    dest_name = os.path.realpath(dest_name)

    # Read the rundata symlink. This may be a relative link so we always
    # convert it to an absolute link by putting it through os.path.realpath()
    rundata_link = os.path.join(afqd, 'rundata')
    rundata_link_dest = os.readlink(rundata_link)
    rundata_link_abs = os.path.realpath(rundata_link)

    if not os.path.isdir(rundata_link_abs):
        # The link is broken. So we'll not touch it.
        L.warning("{} link is invalid. Will not modify links.".format(rundata_link))
        rundata_link_abs = None
    else:
        # output_link needs to be the real path of the link (as opposed to the real path of
        # where the link points!)
        output_link = os.path.join(rundata_link_abs, 'pipeline', 'output')
        output_link_dest = os.readlink(output_link)
        output_link_abs = os.path.realpath(output_link)

        # Now the output_link should point back to afqd or we're in trouble!
        if not output_link_abs == os.path.realpath(afqd):
            L.error("{} link does not point back to {}".format(output_link, afqd))
            return

    # OK we're ready to move the run
    L.info("shutil.move({!r}, {!r})".format(afqd, dest_name))
    if not DRY_RUN:
        shutil.move(afqd, dest_name)
    # And this changes where the rundata link is
    rundata_link = os.path.join(dest_name, 'rundata')

    if rundata_link_abs and rundata_link_abs != rundata_link_dest:
        L.warning("Converting rundata link to an absolute path")
        L.info("os.symlink({!r}, {!r})".format(rundata_link_abs, rundata_link))
        if not DRY_RUN:
            os.unlink(rundata_link)
            os.symlink(rundata_link_abs, rundata_link)

    # And finally, output_link must change unless rundata_link was dangling.
    if rundata_link_abs:
        L.info("os.symlink({!r}, {!r})".format(dest_name, output_link))
        if not DRY_RUN:
            os.unlink(output_link)
            os.symlink(dest_name, output_link)

    L.info("Renamed {} to {}{}".format(afqd, dest_name, " [DRY_RUN]" if DRY_RUN else ""))
    TALLIES['fastqdirs'] += 1

def rebatch_main(args):
    """Performs a batch of move_rundir operations to reflact a desired PROM_RUNS_BATCH mode.
       Rebatching always happens in the CWD.
    """
    runglobs = dict( year  = '0000/00000000_*/',
                     month = '0000-00/00000000_*/',
                     none  = '00000000_*/' )

    # We need to search for directoried matching patterns other than args.mode
    scanglobs = [ v.replace('0', '[0-9]') for k, v in runglobs.items() if k != args.mode ]

    # Now actually look for candidates to rename.
    runs_found = [ d for p in scanglobs for d in glob(p) ]
    L.debug("{} directories match the glob patterns {}".format(len(runs_found), scanglobs))

    runs_found = [ d for d in runs_found if is_rundir(d) ]
    L.debug("{} of these look like actual runs".format(len(runs_found)))
    if not runs_found:
        L.error("Nothing suitable found to rebatch.")
        return

    all_run_bases = set()
    for arun in runs_found:
        # See where it is now.
        run_base, run_name = os.path.split(arun)

        # Work out where it belongs.
        subdir = dict( year  = '{}'.format(run_name[0:4]),
                       month = '{}-{}'.format(run_name[0:4], run_name[4:6]),
                       none  = '' )[args.mode]

        # Remember the run base for later
        if run_base:
            all_run_bases.add(run_base)

        # Make a home for it
        if subdir:
            try:
                if not DRY_RUN:
                    os.mkdir(subdir)
                L.debug("Created subdir {}".format(subdir))
            except OSError:
                # Presumably it exists
                pass

        # Finally move the thing.
        dest_name = os.path.join(os.path.realpath('.'), subdir, run_name)
        move_rundir(arun, dest_name)

    # After renaming all, clean empty directories.
    for d in all_run_bases:
        try:
            if not DRY_RUN:
                os.rmdir(d)
            L.debug("Removed now-empty directory {}".format(d))
        except OSError:
            # Probably not empty.
            pass

def parse_args(*args):
    description = """Moves a Hesiod rundir or fastqdir, or else bulk moves all directories
                     to an alternative PROM_RUNS_BATCH mode.
                  """
    parser = ArgumentParser( description=description,
                             formatter_class = ArgumentDefaultsHelpFormatter )
    sparsers = parser.add_subparsers()

    # mv mode
    parser_mv = sparsers.add_parser('mv', help="Move a rundir or fastqdir")
    parser_mv.add_argument('-t', '--to_dir', default='.')
    parser_mv.add_argument('runs', nargs='+')
    parser_mv.set_defaults(func=mv_main) # as suggested in the docs.

    parser_rebatch = sparsers.add_parser('rebatch', help="Rebatch all rundirs in CWD")
    parser_rebatch.add_argument('mode', choices='year month none'.split())
    parser_rebatch.set_defaults(func=rebatch_main)

    parser.add_argument("-d", "--debug", action="store_true",
                        help="Print more verbose debugging messages.")
    parser.add_argument("-n", "--no_act", action="store_true",
                        help="Dry run only.")

    return parser.parse_args(*args)

if __name__ == "__main__":
    main(parse_args())

