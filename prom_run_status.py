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
    CELL_PENDING    = 0   # waiting for data from the sequencer (ie. from rsync)
    CELL_READY      = 1   # the pipeline should process this cell now (ie. sync done)
    CELL_PROCESSING = 2   # the pipeline is working on this cell
    CELL_PROCESSED  = 3   # the pipeline has finished on this cell
    CELL_FAILED     = 4   # the pipeline failed to process this cell
    CELL_ABORTED    = 5   # cell aborted - disregard it

    def __init__( self, run_dir, opts='', remote_cells=None , stall_time=None ):

        # Are we auto-aborting stalled cells like SMRTino?
        self.stall_time = int(stall_time) if stall_time is not None else None

        if os.path.exists(os.path.join(run_dir, 'prom_run', 'pipeline')):
            # We seem to be running in an existing output directory
            self.to_path = pbrun_dir
            self.from_path = os.path.join(run_dir, 'prom_run')
        else:
            # Assume we're in an input directory. This should have been created with
            # a valid pipeline/output link already.
            self.to_path = os.path.join(run_dir, 'pipeline', 'output')
            self.from_path = pbrun_dir

            if not os.path.isdir(self.to_path):
                # Status will be unknown but we might still get some further info
                self._assertion_error = True

        # We need this so we can meaningfully inspect basename(from_path) even if
        # run_dir == '.'
        from_path = os.path.abspath(self.from_path)
        self.remote_cells = (remote_cells or {}).get(os.path.basename(from_path), tuple())

        # Do we need a quick mode?
        self.quick_mode = 'q' in opts

        self._clear_cache()

    def _clear_cache( self ):
        self._exists_cache = dict()
        #self._cells_cache = None

    def _exists_from( self, glob_pattern ):
        """ Returns if a file exists in from_path and caches the result.
        """
        return self._exists(glob_pattern, self.from_path)

    def _exists_to( self, glob_pattern ):
        """ Returns if a file exists in to_path and caches the result.
        """
        return self._exists(glob_pattern, self.to_path)

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

    def get_cells( self ):
        """ Returns a dict of { cellname: status } where status is one of the constants
            defined above
            We assume that all of the directories appear right when the run starts, and
            that a .transferdone file signals the cell is ready
        """
        if self._cells_cache is not None:
            return self._cells_cache

        # OK, we need to work it out...
        res = dict()
        cells = glob( os.path.join(self.from_path, '[0-9]_???/') )

        for cell in cells:
            cellname = cell.rstrip('/').split('/')[-1]

            if self._exists_to( 'pbpipeline/' + cellname + '.aborted' ):
                res[cellname] = self.CELL_ABORTED
            elif self._exists_to( 'pbpipeline/' + cellname + '.failed' ):
                # Not sure if we need this?
                res[cellname] = self.CELL_FAILED
            elif self._exists_to( 'pbpipeline/' + cellname + '.done' ):
                res[cellname] = self.CELL_PROCESSED
            elif self._exists_to( 'pbpipeline/' + cellname + '.started' ):
                res[cellname] = self.CELL_PROCESSING
            elif self._exists_from( cellname + '/*.transferdone' ):
                res[cellname] = self.CELL_READY
            else:
                res[cellname] = self.CELL_PENDING

        self._cells_cache = res
        return res

    def _was_aborted(self):
        if self._exists_to( 'pbpipeline/aborted' ):
            return True

        # Or if all idividual cells were aborted...
        all_cell_statuses = self.get_cells().values()
        if all_cell_statuses and all( v == self.CELL_ABORTED for v in all_cell_statuses ):
            return True

        return False

    def _is_stalled(self):
        if self.stall_time is None:
            # Nothing is ever stalled then.
            return False

        # Now some datetime tinkering...
        # If I find something dated later than stall_time then this run is not stalled.
        # It's simpler to just get this as a Unix time that I can compare with stat() output.
        stall_time = ( datetime.datetime.now(datetime.timezone.utc)
                       - datetime.timedelta(hours=self.stall_time)
                     ).timestamp()

        for cell in glob( os.path.join(self.from_path, '[0-9]_???') ):

            if os.stat(cell).st_mtime > stall_time:
                # I only need to see one thing
                return False

        # I found no evidence.
        return True

    def get_status( self ):
        """ Work out the status of a run by checking the existence of various touchfiles
            found in the run folder.
            Behaviour with the touchfiles in invalid states is undefined, but we'll always
            report a valid status and in general, if in doubt, we'll report a status that
            does not trigger an action.
            ** This logic is convoluted. Before modifying anything, make a test that reflects
               the change you want to see, then after making the change always run the tests.
               Otherwise you will get bitten in the ass!
        """
        # If one of the sanity checks failed the status must be unknown - any action would
        # be dangerous.
        if self._assertion_error:
            return "unknown"

        # Otherwise, 'new' takes precedence
        if not self._exists_to( 'pbpipeline' ):
            return "new"

        # Run in aborted state should not be subject to any further processing
        if self._was_aborted():
            return "aborted"

        # No provision for 'redo' state just now, but if there was this would need to
        # go in here to override the failed and complete statuses.

        if self._exists_to( 'pbpipeline/report.done' ):
            if self._exists_to( 'pbpipeline/failed' ):
                return "failed"
            else:
                return "complete"

        if self._exists_to( 'pbpipeline/report.started' ):
            # Even if reporting is very quick, we need a state for the run to be in while
            # it is happening. Alternative would be that driver triggers report after processing
            # the last SMRT cell, before marking the cell done, but this seems a bit flakey.
            if self._exists_to( 'pbpipeline/failed' ):
                return "failed"
            else:
                return "reporting"

        # The 'failed' flag is going to be set if a report fails to generate or there is an
        # RT error or summat like that.
        # But until the final report is generated, the master 'failed' flag is ignored, so it's
        # possible that an interim report fails but then a new cell gets processed and the report
        # is re-triggered and this time it works and the flag can be cleared. Yeah.

        # At this point we need to know which SMRT cells are ready/done. Disregard aborted cells.
        # If everything was aborted we'll already have decided status='aborted'

        # As with Illuminatus, this logic is a little contorted. The tests reassure me that all is
        # well. If you see a problem add a test case before attempting a fix.

        all_cell_statuses = [ v for v in self.get_cells().values() if v != self.CELL_ABORTED ]

        # If any cell is ready we need to get it processed
        if any( v == self.CELL_READY for v in all_cell_statuses ):
            return "cell_ready"

        # If all are processed we're in state processed, and ready to trigger the final report
        if all_cell_statuses and all( v == self.CELL_PROCESSED for v in all_cell_statuses ):
            return "processed"

        # If all cells are processed or failed we're in state failed
        # (otherwise delay failure until all cells are accounted for)
        if all_cell_statuses and all( v in [self.CELL_FAILED, self.CELL_PROCESSED] for v in all_cell_statuses ):
            return "failed"

        # If none are processing we're in state 'idle_awaiting_cells'. This also applies if,
        # for some reason, the list of cells is empty.
        # At this point, we should also check if the run might be stalled.
        if all( v not in [self.CELL_PROCESSING] for v in all_cell_statuses ):
            if self._is_stalled():
                return "stalled"
            else:
                return "idle_awaiting_cells"

        # If any are pending we're in state 'processing_awaiting_cells'
        if any( v == self.CELL_PENDING for v in all_cell_statuses ):
            return "processing_awaiting_cells"

        # Otherwise we're processing but not expecting any more data
        return "processing"

    def get_cells_ready(self):
        """ Get a list of the cells which are ready to be processed, if any.
        """
        return [c for c, v in self.get_cells().items() if v == self.CELL_READY]

    def get_cells_aborted(self):
        """ Get a list of the cells that were aborted, if any.
        """
        return [c for c, v in self.get_cells().items() if v == self.CELL_ABORTED]

    def get_run_id(self):
        """ We can read this from RunDetails in any of the subreadset.xml files, but it's
            easier to just assume the directory name is the run name. Allow a .xxx extension
            since there are no '.'s is PacBio run names.
        """
        realdir = os.path.basename(os.path.realpath(self.from_path))
        return realdir.split('.')[0]

    def get_instrument(self):
        """ We have only one and the serial number is in the run ID
        """
        foo = self.get_run_id().split('_')[0]
        if foo.startswith('r') and len(foo) > 1:
            return "Sequel_" + foo[1:]
        else:
            return 'unknown'

    def get_start_time(self):
        """ Look for the oldest *.txt file in any subdirectory.
        """
        txtfiles = glob( os.path.join(self.from_path, '[0-9]_???/*.txt') )

        try:
            oldest_time = min( os.stat(t).st_mtime for t in txtfiles )

            return datetime.datetime.fromtimestamp(oldest_time).ctime()

        except Exception:
            return 'unknown'

    def get_yaml(self, debug=True):
        try:
            return '\n'.join([ 'RunID: '        + self.get_run_id(),
                               'Instrument: '   + self.get_instrument(),
                               'Cells: '        + ' '.join(sorted(self.get_cells())),
                               'CellsReady: '   + ' '.join(sorted(self.get_cells_ready())),
                               'CellsAborted: ' + ' '.join(sorted(self.get_cells_aborted())),
                               'StartTime: '    + self.get_start_time(),
                               'PipelineStatus: ' + self.get_status() ])

        except Exception: # if we can't read something just produce a blank reply.
            if debug: raise
            pstatus = 'aborted' if self._was_aborted() else 'unknown'

            return '\n'.join([ 'RunID: unknown',
                               'Instrument: unknown',
                               'Cells: ',
                               'CellsReady: ',
                               'CellsAborted: ',
                               'StartTime: unknown',
                               'PipelineStatus: ' + pstatus ])

if __name__ == '__main__':
    # Very cursory option parsing
    optind = 1 ; opts = ''
    if sys.argv[optind:] and sys.argv[optind].startswith('-'):
        optind += 1
        opts = sys.argv[optind][1:]

    L.basicConfig(level=L.WARNING, stream=sys.stderr)

    # Load the remote cell list from STDIN
    if 'N' in opts:
        remote_cells = {}
    else:
        remote_cells = parse_remote_cell_info()

    # If no run specified, examine the CWD.
    runs = sys.argv[optind:] or ['.']
    for run in runs:
        run_info = RunStatus(run, opts,
                             remote_cells = remote_cells,
                             stall_time  = os.environ.get('STALL_TIME') or None)
        print ( run_info.get_yaml( debug=os.environ.get('DEBUG', '0') != '0' ) )
