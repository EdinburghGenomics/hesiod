#!/usr/bin/env python3
import os.path
from glob import glob
import sys
import logging as L
import datetime

class RunStatus:
    """This Class provides information about a Promethion run, given a run folder.
       It will look in the pipeline directory for touch files that indicate the
       status.
       The status will correspond to a state in the state diagram - see the design doc.
    """
    CELL_NEW        = -1  # completely new cell from the sequencer (ie. from rsync)
    CELL_PENDING    = 0   # waiting for data from the sequencer (ie. from rsync)
    CELL_READY      = 1   # the pipeline should process this cell now (ie. sync done)
    CELL_PROCESSING = 2   # the pipeline is working on this cell
    CELL_PROCESSED  = 3   # the pipeline has finished on this cell
    CELL_FAILED     = 4   # the pipeline failed to process this cell
    CELL_ABORTED    = 5   # cell aborted - disregard it
    CELL_INCOMPLETE = 6   # cell is not ready but there is no remote to fetch

    def __init__( self, run_dir, opts='', upstream=None , stall_time=None ):

        # Are we auto-aborting stalled cells like SMRTino?
        self.stall_time = int(stall_time) if stall_time is not None else None

        if os.path.exists(os.path.join(run_dir, 'rundata', 'pipeline')):
            # We seem to be running in an existing output directory
            self.fastqdata_path = run_dir
            self.run_path = os.path.join(run_dir, 'rundata')
        else:
            # Assume we're in an input directory. This should have been created with
            # a valid pipeline/output link already, unless it's local and new.
            self.fastqdata_path = os.path.join(run_dir, 'pipeline', 'output')
            self.run_path = run_dir

        remote_info_for_run = (upstream or {}).get(self.get_experiment(), dict())
        self.remote_cells = remote_info_for_run.get('cells', set())
        self.remote_loc = remote_info_for_run.get('loc', None)

        # Cell names are in the form library/cell as there are two levels of directory.
        # Note the glob pattern needs to be the same as in list_remote_cells.sh
        self.local_cells = set()
        for l in glob( os.path.join(self.run_path, '*/20??????_*_????????/fast?_????') ):
            self.local_cells.add("{}/{}".format(*l.split('/')[-3:]))

        # Do we need a quick mode?
        self.quick_mode = 'q' in opts

        self._clear_cache()

    def _clear_cache( self ):
        self._exists_cache = dict()
        self._cells_cache = None

    def _exists_pipeline( self, glob_pattern ):
        """ Returns if a file exists in the pipeline dir and caches the result.
        """
        return self._exists(glob_pattern, self.run_path + '/pipeline')

    def _exists( self, glob_pattern, root_path ):
        """ Returns if a file exists in root_path and caches the result.
            The check will be done with glob() so wildcards can be used, and
            the result will be the number of matches.
        """
        full_pattern = os.path.join(root_path, glob_pattern)
        if full_pattern not in self._exists_cache:
            self._exists_cache[full_pattern] = glob(full_pattern)
            L.debug("_exists {} => {}".format(full_pattern, self._exists_cache[full_pattern]))

        return len( self._exists_cache[full_pattern] )

    def cell_to_tfn(self, cellname):
        """This corresponds to cell_to_tfn in driver.sh
           tfn stands for touch file name
        """
        return cellname.split('/')[-1]

    def get_cells( self ):
        """ Returns a dict of { cellname: status } where status is one of the constants
            defined above.
        """
        if self._cells_cache is not None:
            return self._cells_cache

        # OK, we need to work it out...
        res = dict()

        for cellname in self.local_cells:

            tfn = self.cell_to_tfn(cellname)

            if self._exists_pipeline( tfn + '.aborted' ):
                res[cellname] = self.CELL_ABORTED
            elif self._exists_pipeline( tfn + '.done' ):
                res[cellname] = self.CELL_PROCESSED
            elif self._exists_pipeline( tfn + '.started' ):
                res[cellname] = self.CELL_PROCESSING
            elif self._exists_pipeline( tfn + '.synced' ):
                res[cellname] = self.CELL_READY
            elif cellname in self.remote_cells:
                res[cellname] = self.CELL_PENDING
            else:
                # It's not ready for processing but there is no upstream?
                # Maybe the upstream is unreachable just now.
                res[cellname] = self.CELL_INCOMPLETE

        # Now factor in the remote stuff. Only compare the suffixes here
        # to allow for reasonable behaviour if a library is locally renamed.
        # If a library is renamed before the sync finishes then it will not
        # continue to sync, but I don't think I need to make that work.
        local_tfn_set = set([self.cell_to_tfn(c) for c in res])
        for cellname in self.remote_cells:
            tfn = self.cell_to_tfn(cellname)
            if not tfn in local_tfn_set:
                res[cellname] = self.CELL_NEW

        self._cells_cache = res
        return res

    def _was_aborted(self):
        return self._exists_pipeline( 'aborted' )

    def _was_stripped(self):
        # The data deleter adds this
        return self._exists_pipeline( 'stripped' )

    def _is_stalled(self):
        """ This works in SMRTino. It may or may not be sensible here.
            FIXME or DELETEME
        """

        if self.stall_time is None:
            # Nothing is ever stalled then.
            return False

        # Now some datetime tinkering...
        # If I find something dated later than stall_time then this run is not stalled.
        # It's simpler to just get this as a Unix time that I can compare with stat() output.
        stall_time = ( datetime.datetime.now(datetime.timezone.utc)
                       - datetime.timedelta(hours=self.stall_time)
                     ).timestamp()

        for cell in self.local_cells:

            if os.stat(cell).st_mtime > stall_time:
                # I only need to see one thing
                return False

        # I found no evidence.
        return True

    def get_status( self ):
        """ Work out the status of a run by checking the existence of various touchfiles
            found in the run folder.
            Behaviour with the touchfiles in invalid states is undefined, but we'll always
            report some sort of status and in general, if in doubt, we'll report a status that
            does not trigger an action.
            ** This logic is convoluted. Before modifying anything, make a test that reflects
               the change you want to see, then after making the change always run the regression
               tests. Otherwise you will get in a mess.
        """
        # Otherwise, 'new' takes precedence.
        # (Note if there is no pipeline directory but there is a fastqdata/{run_name} directory
        # then we still report status=new. driver.sh will deal with the error.)
        if not self._exists_pipeline('.'):
            return "new"

        # Experiment in aborted state should not be subject to any further processing
        # But beware - it's still possible that the lab could add cells to the experiment, so
        # best to abort the individual cells.
        if self._was_aborted():
            return "aborted"

        # If the data deletion process has stripped out the run. But then I'd expect
        # archive_pack_prom_runs.sh to quickly mop up the remains? Hmmmm.
        if self._was_stripped():
            return "stripped"

        # No provision for 'redo' state just now, but if there was this would need to
        # go in here to override the failed and complete statuses.

        # For now, I'm going to say that the presence of the master 'failed' flag makes
        # the run failed. SMRTino has some provision for an intermittent failure that then
        # gets cleared when the run completes, but here I don't think that works.
        if self._exists_pipeline( 'failed' ):
            return "failed"

        # Now look at the cells. If all are non-aborted cells are complete we're done.
        all_cell_statuses = self.get_cells().values()

        # Are we OK to rsync? I'm going to assume that if sync.failed then we are allowed to
        # try again. If not, then the presence of sync.failed when no cell is ready to process
        # or processing should lead to state=failed
        sync_in_progress = ( self._exists_pipeline( 'sync.started' ) and
                             not self._exists_pipeline( 'sync.done' ) and
                             not self._exists_pipeline( 'sync.failed' ) )

        if all( s in [self.CELL_PROCESSED, self.CELL_ABORTED] for s in all_cell_statuses):
            if sync_in_progress:
                # This happens when new cells are being synced but then you inspect
                # the status without supplying the upstream info.
                return "syncing"
            else:
                return "complete"

        # If the output path is missing then we don't want to trigger any actions.
        if not os.path.isdir(self.fastqdata_path):
            return "unknown"

        # Is anything waiting to sync?
        sync_needed = any( s in [self.CELL_PENDING, self.CELL_NEW] for s in all_cell_statuses )

        # Is anything being processed just now?
        processing_now = any( s in [self.CELL_PROCESSING] for s in all_cell_statuses )

        # If the run is processing we definitely need some sort of 'processing' status. This
        # may possibly still trigger a sync if one is needed and none is on progress.
        if processing_now and sync_needed:
            if sync_in_progress:
                return "processing_syncing"
            else:
                return "processing_sync_needed"
        elif processing_now:
            if sync_in_progress:
                # Eh? Why is an rsync in progress if nothing is pending?
                return "processing_syncing"
            else:
                return "processing"
        elif any( v in [self.CELL_READY] for v in all_cell_statuses ):
            # Is anything needing processed? If no processing is ongoing we
            # choose to kick off processing in preference to sync.
            return "cell_ready"
        elif sync_in_progress:
            return "syncing"
        elif sync_needed:
            return "sync_needed"

        if self._is_stalled():
            # Not sure if we are having stalled state yet, but if so...
            return "stalled"

        if any( s in [self.CELL_INCOMPLETE] for s in all_cell_statuses ):
            return "incomplete"

        # Is anything failed?
        if any( s in [self.CELL_FAILED] for s in all_cell_statuses ):
            return "failed"

        # Dunno. I give up.
        return "unknown"

    def get_cells_in_state(self, *states):
        """ Get a list of the cells which are ready to be processed, if any.
        """
        return [c for c, v in sorted(self.get_cells().items()) if v in states]

    def get_experiment(self):
        """ The directory name is the experiment name. Allow a .xxx extension
            since there are no '.'s is PacBio run names.
        """
        realdir = os.path.basename(os.path.realpath(self.run_path))
        return realdir.split('.')[0]

    def get_instrument(self):
        """ This is controlled by the UPSTREAM setting and goes as the second
            part of the run ID.
        """
        try:
            return self.get_experiment().split('_')[1]
        except IndexError:
            return "unknown"

    def get_start_time(self):
        """ Is there a good way to do this? For remote runs this depends on RSYNC
            fixing the local time stamps.
        """
        somefiles = glob( os.path.join(self.run_path, '*/*_*_*_*/*_*') )

        try:
            oldest_time = min( os.stat(t).st_mtime for t in somefiles )

            return datetime.datetime.fromtimestamp(oldest_time).ctime()

        except Exception:
            return 'unknown'

    def get_yaml(self, debug=True):
        try:
            return '\n'.join([ 'Experiment: '   + self.get_experiment(),
                               'Instrument: '   + self.get_instrument(),
                               'Upstream: '     + (self.remote_loc or 'LOCAL'),
                               'Cells: '        + '\t'.join(sorted(self.get_cells())),
                               'CellsPending: ' + '\t'.join(self.get_cells_in_state(self.CELL_NEW,
                                                                                    self.CELL_PENDING,
                                                                                    self.CELL_INCOMPLETE)),
                               'CellsReady: '   + '\t'.join(self.get_cells_in_state(self.CELL_READY)),
                               'CellsDone: '    + '\t'.join(self.get_cells_in_state(self.CELL_PROCESSED)),
                               'CellsAborted: ' + '\t'.join(self.get_cells_in_state(self.CELL_ABORTED)),
                               'StartTime: '    + self.get_start_time(),
                               'PipelineStatus: ' + self.get_status() ])

        except Exception: # if we can't read something just produce a blank reply.
            if debug: raise
            pstatus = 'aborted' if self._was_aborted() else 'unknown'

            return '\n'.join([ 'Experiment: ' + self.get_experiment(),
                               'Instrument: unknown',
                               'Upstream: unknown',
                               'Cells: ',
                               'CellsToSync: ',
                               'CellsReady: ',
                               'CellsDone: ',
                               'CellsAborted: ',
                               'StartTime: unknown',
                               'PipelineStatus: ' + pstatus ])

def parse_remote_cell_info():
    """Read a list of TSV lines form STDIN - run_id + remote_loc + remote_cell
       There may be multiple lines relating to each run_id, but the location should
       be the same for each.
       Also the first part of the path should be the same for each.
    """
    res = dict()

    for l in sys.stdin:
        if not l.strip(): continue
        run_id, loc, cell = l.strip().split('\t')

        run_infos = res.setdefault(run_id, dict())

        run_infos.setdefault('loc', loc)
        run_infos.setdefault('cells', set()).add(cell)

    return res

if __name__ == '__main__':
    # Very cursory option parsing
    optind = 1 ; opts = ''
    if sys.argv[optind:] and sys.argv[optind].startswith('-'):
        opts = sys.argv[optind][1:]
        optind += 1

    L.basicConfig(level=L.WARNING, stream=sys.stderr)

    # Load the remote cell list from STDIN
    if not 'I' in opts:
        remote_info = {}
    else:
        remote_info = parse_remote_cell_info()

    # If no run specified, examine the CWD.
    runs = sys.argv[optind:] or ['.']
    for run in runs:
        run_info = RunStatus(run, opts,
                             upstream = remote_info,
                             stall_time  = os.environ.get('STALL_TIME') or None)
        print ( run_info.get_yaml( debug=os.environ.get('DEBUG', '0') != '0' ) )
