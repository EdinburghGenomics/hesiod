#!/usr/bin/env python3
import os, sys, re
import logging as L
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from pprint import pformat
from math import modf
from datetime import datetime
from collections import OrderedDict
import shutil

from hesiod import hesiod_version, glob, load_yaml, abspath, groupby

# Things we don't want to see in the Metadata section (as it's too cluttered)
METADATA_HIDE = set('''
    Run       Experiment   Cell            Base            Date
    Number    Checksum     Fast5Version    BaseCallerTime  UpstreamExpt
'''.split())

def format_counts_per_cells(cells, heading="Read summary"):
    """I broke this out of format_report(). It takes counts for a bunch of cells and adds
       them up, over all barcodes - normally this is done for all cells belonging to a project.
    """
    # Tabulate some totals for passed/failed/filtered. This is just a matter of totting
    # up values in the _counts section of each cell. Now more complex since cells have barcodes.
    counts_by_barcode = [ groupby(c['_counts'], lambda f: f.get('_barcode', '.'))
                          for c in cells ]
    # Flatten the list of dicts of lists into a list of [3-item] lists
    all_counts = [ v for cbb in counts_by_barcode for v in cbb.values() ]

    # Get all the labels from the first barcode of the first cell:
    labels = [f['_label'] for f in all_counts[0]]

    # And sanity check that the list of labels is consistent for all cells
    # (as from here we'll assume everything is in the same order)
    for c in all_counts[1:]:
        assert [f['_label'] for f in c] == labels

    # A list of lists to populate the table
    # see test/test_make_report.py if you're trying to work out how the nested
    # expansions work.
    rows = [ ( label,
               sum( cat_counts['total_reads'] ),
               sum( cat_counts['total_bases'] ),
               max( cat_counts['max_length'] ) )
             for row, label in enumerate(labels)
             for cat_counts in [{ k: [ c[row][k] for c in all_counts ]
                                  for k in ['total_reads', 'total_bases', 'max_length'] }] ]

    return( format_table( ["Part", "Total Reads", "Total Bases", "Max Length"],
                          rows,
                          title = heading ) )

def get_cell_summary( all_info ):
    """ Make a table of this stuff, one row per cell...
            Experiment Name - upstream name
            Sample ID - easy. first part of cell ID
            Run ID - the uuid
            Flow Cell ID - PAMXXXX
            Run Length - get from the final summary
            Reads Generated (M) - we have this in cell_info.yaml (pass and fail)
            Estimated Bases (Gb) - ditto
            Passed Bases (Gb) - ditto (and we can give a percentage)
            Estimated N50 (kb) - NanoStats.yaml has this (or NanoStats.txt)
    """
    # all_info is a dict of cell_name => info_dict
    return [], []

def format_report( all_info,
                   pipedata,
                   aborted_list = (),
                   minionqc = None,
                   totalcells = None,
                   project_realnames = None,
                   blobstats = None ):
    """Makes the report as a list of strings (lines)
    """
    P = aggregator()

    # Get the experiments(s). In older YAMLs this was recorded as 'Run'
    expts = sorted(set([ i.get('Experiment', i.get('Run')) for i in all_info.values() ]))
    # We also may have the original Experiment name (without the date and machine ID)
    upstream_expts = sorted(set([ i.get('UpstreamExpt') for i in all_info.values() ]))

    # Just in case of missing info
    expts = [ e for e in expts if e ] or ["No name"]
    upstream_expts = [ e for e in upstream_expts if e ] or ["Not set"]

    #instr = sorted(set([ i['Run'].split('_')[1] for i in all_info.values() ]))
    libs = sorted(set([ i['Cell'].split('/')[0] for i in all_info.values() ]))

    #########################################################################
    # Header
    #########################################################################

    P( f"% Promethion experiment {','.join(expts)}",
       f"% Hesiod version {pipedata['version']}",
       f"% {datetime.now().strftime('%A, %d %b %Y %H:%M')}" )

    #########################################################################
    # Run metadata
    #########################################################################
    P()
    P( "# About this experiment\n")

    P( format_dl( [( 'Experiment',          ",".join(expts) ),
                   ( 'Upstream Experiment', ",".join(upstream_expts) ),
                   ( 'Upstream Location',   pipedata['upstream'] ),
                   #( 'Instrument',         ",".join(instr) ),
                   ( 'Cell Count',          len(all_info) if totalcells is None else totalcells ),
                   ( 'Library Count',       len(libs) ),
                   ( 'Start Time',          (pipedata['start_times'] or ['unknown'])[0] ),
                   ( 'Last Run Time',       (pipedata['start_times'] or ['unknown'])[-1], )],
                  title="Metadata") )

    # Table of stuff used that was being for sign-off so I'm auto-adding it
    cs_headings, cs_rows = get_cell_summary(all_info)
    P( format_table( cs_headings,
                     cs_rows,
                     title = "Cell summary" ) )

    # Overview plots from minionqc/combinedQC
    if minionqc:
        mqc_header = "MinionQC: Combined Length Histo ; Combined Quality Histo ; Combined Yield over Time"
        P(f"\n### {mqc_header}\n")
        P("<div class='flex'>")
        P(" ".join(
            f"[plot](img/minqc_combined_{x}.png){{.thumbnail}}"
            for x in ['combined_length_histogram', 'combined_q_histogram', 'yield_over_time']
         ))
        P("</div>")

    #########################################################################
    # Per-project section
    #########################################################################

    # Info and BLOB stats by project, which we get from i['Project']. Hopefully the LIMS gave us names
    # and links to all the projects.
    P( "\n# Stats per project\n")
    for p, title, cells in list_projects( all_info.values(), project_realnames ):

        # No escaping of title - list_projects adds MD markup already
        P( f"## {title}\n" )
        P()
        P( ":::::: {.bs-callout}" )

        # Calculate some basic metadata for all cells in project
        # Note that "ci['Files in '+pf]" is set in Snakefile.main and here we assume that all the
        # values are nice integers.
        P( format_dl( [( 'Cell Count', len(cells) ),
                       ( 'Library Count', len(set([c['Library'] for c in cells])) ),
                       ( 'Files in pass', sum(c['Files in pass'] for c in cells) ),
                       ( 'Files in fail', sum(c['Files in fail'] for c in cells) )],
                      title="Metadata") )

        # Number of sequences/bases in passed/failed
        P( format_counts_per_cells(cells) )

        # Now for the BLOB tables. These are specified by the blobstats_by_project.yaml file,
        # and will be loaded as a dict by project.
        # Simply print all the tables listed.
        for blobtable in (blobstats or {}).get(p, []):

            # Insert the table as it comes
            P( format_table( blobtable['tsv_data'][0],
                             blobtable['tsv_data'][1:],
                             title = blobtable['title'] ))

        P( "", "::::::", "" )


    #########################################################################
    # Per-cell section
    #########################################################################

    P('\n# Stats per cell\n')
    for cell, ci in sorted(all_info.items()):
        P()
        P( f"## Cell {cell}" )
        P()

        # If there is a MinKNOW report then add it here
        if ci.get('_minknow_report'):
            rep_filename = os.path.basename(ci['_minknow_report'])
            P( f"[MinKNOW PDF Report](minknow/{rep_filename})" )
            P()

        P( ":::::: {.bs-callout}" )

        # We'll need this shortly. See copy_files
        cell_uid = ci['Base'].split('/')[-1]

        def _format(_k, _v):
            """Handle special case for dates"""
            if _k == "Date" and re.match(r'[0-9]{8}', _v):
                _v = datetime.strptime(_v, '%Y%m%d').strftime('%d %b %Y')
            return (_k, _v)

        # Now the metadata section
        P( format_dl( [ _format( k, v ) for k, v in ci.items()
                        if not ( k.startswith("_")
                                 or k in METADATA_HIDE ) ],
                      title="Metadata") )

        # Stuff from the .count files that's been embedded in the YAML.
        # Make a single table
        if ci.get('_counts'):
            headings = [ h for h in ci['_counts'][0] if not h.startswith('_') ]

            # Confirm that all dicts have the same labels
            for c in ci['_counts'][1:]:
                assert [ h for h in c if not h.startswith('_') ] == headings

            # Reformat the values into rows
            rows = [ [ c['_label'] ] + [ c[h] for h in headings ]
                     for c in ci['_counts'] ]

            P( format_table( ["Part"] + [ fixcase(h) for h in headings ],
                             rows,
                             title = "Read counts" ) )
            P()


        # Nanoplot stats
        if '_nanoplot_data' in ci:
            ns = ci['_nanoplot_data']

            def _format(_k, _v):
                """Coerce some floats to ints but not all of them"""
                if not( _k.startswith("Mean") or _k.startswith("Median") ):
                    # We believe the float is really an int in disguise
                    if not modf(_v)[0]:
                        _v = int(_v)
                return (_k, _v)

            if ns:
                # So we just want the General summary. But do we want it as a table or a
                # DL or a rotated table or what? Let's have all three.
                nsgs, = [ i[1] for i in ns if i[0] == "General summary" ]

                '''
                # As I had it before
                P( format_dl( [ (k, pv) for k, pv, *_ in nsgs ],
                              title = "Nanoplot general summary" ) )

                # As a one-line table, using the number values
                P( format_table( [ k for k, pv, nv, *_ in nsgs ],
                                 [ [ _format(k, nv)[1] for k, pv, nv, *_ in nsgs ] ],
                                 title = "Nanoplot general summary" ) )
                '''

                # As a rotated table
                P( format_table( ['Item', 'Printable', 'Value'],
                                 [ [k, pv, _format(k, nv)[1] ] for k, pv, nv, *_ in nsgs ],
                                 title = "Nanoplot general summary" ) )

            else:
                # Here we have an empty report (as opposed to a missing report)
                P( format_table( ['Item', 'Printable', 'Value'],
                                 [ ('Passing reads', '0', '0') ],
                              title = "Nanoplot general summary" ) )

            # Version that prints everything...
            '''
            for title, items in ns:
                P( '<dl class="dl-horizontal">' )
                P("### Nanoplot {}\n".format(escape_md(title)))
                for k, pv, *_ in items:
                    P('<dt>{}</dt> <dd>{}</dd>'.format(escape_md(k),escape_md(pv)))
                P( '</dl>' )
                P()
            '''

        # Embed some files from MinionQC
        if '_minionqc' in ci:
            mqc_header = "MinionQC: Length Histo ; Length vs Qual ; Yield over Time"
            P(f"\n### {mqc_header}\n")
            P("<div class='flex'>")
            P(" ".join(
                f"[plot](img/minqc_{cell_uid}_{f}.png){{.thumbnail}}"
                for f in ['length_histogram', 'length_vs_q', 'yield_over_time']
             ))
            P("</div>")

        # Nanoplot plots
        if '_nanoplot' in ci:
            nplot_header = "NanoPlot: Length Histo ; Length vs Qual ; Yield over Time ; Active Pores over Time"
            P(f"\n### {nplot_header}\n")
            P("<div class='flex'>")
            P(" ".join(
                f"[plot](img/nanoplot_{cell_uid}_{x}.png){{.thumbnail}}"
                for x in [ 'HistogramReadlength',
                           'LengthvsQualityScatterPlot_dot',
                           'NumberOfReads_Over_Time',
                           'ActivePores_Over_Time' ]
             ))
            P("</div>")


            # Link to the NanoPlot report
            P( f"[Full NanoPlot Report](np/NanoPlot_{cell_uid}-report.html)" )

        # Blob plots as per SMRTino (the YAML file is linked rather than embedded but it's the
        # same otherwise). Often we have barcodes with no passed reads, in which case 'has_data'
        # will be set to False and we skip the plot.
        if '_blobs_data' in ci:
            for ablob in ci['_blobs_data']:
                for plot_group in ablob:
                    if plot_group.get('has_data') is False:
                        continue

                    P(f"\n### {plot_group['title']}\n")

                    # plot_group['files'] will be a a list of lists, so plot
                    # each list a s a row.
                    for plot_row in plot_group['files']:
                        P("<div class='flex'>")
                        P(" ".join(
                            f"[plot](img/{os.path.basename(p)}){{.thumbnail}}"
                            for p in plot_row
                         ))
                        P("</div>")

        P( "::::::" )

    P()
    P("*~~~*")
    return P

def format_dl(data_pairs, title=None):
    """Formats a table of values with headings in the first column.
       Currently we do this as a <dl>, but this may change.
    """
    P = aggregator()

    P( '<dl class="dl-horizontal">' )
    if title:
        P(f"### {escape_md(title)}\n")
    for k, pv in data_pairs:
        P(f"<dt>{escape_md(k)}</dt> <dd>{escape_md(pv)}</dd>")
    P( '</dl>' )
    P()

    return "\n".join(P)

def format_table(headings, data, title=None):
    """Another markdown table formatter. Values will be escaped.
       Presumably the table is destined to be a DataTable.
       Returns a single string.
    """
    P = aggregator()

    if title:
        P(f"### {escape_md(title)}\n")

    # Add the header, bounded by pipes.
    P('| {} |'.format( ' | '.join([ escape_md(h)
                                    for h in headings ]) ))

    # Add the spacer line - fix the with for easier reading of the MD
    widths = [ len(escape_md(h)) for h in headings ]
    P('|-{}|'.format( '|-'.join([ "-{:-<{w}s}".format('', w=w)
                                  for w in widths ]) ))

    # Add the data.
    for drow in data:
        P('| {} |'.format( ' | '.join([ escape_md(d)
                                        for d in drow ]) ))
    P()

    return "\n".join(P)

def load_cell_yaml(filename):
    """Load the YAML and fix the counts.
       I copied the .count format from Illuminatus where most FASTQ files have all sequences the
       same length, but here this is rarely the case and I have read_length as a string '<min>-<max>'.
       Rather than change the format and have to re-count all files, I'll just cope with the old
       format here.
    """
    celldict = load_yaml(filename)

    # We sort by cell ID so all YAML must have this.
    assert celldict.get('Cell'), "All yamls must have a Cell ID"
    assert celldict.get('Project'), "All yamls must have a Project (recreate this file with the latest Snakefile)"

    for countsdict in celldict.get('_counts', []):
        if 'read_length' in countsdict:
            # This works if the read length is already an int or a single string
            rlsplit = str(countsdict['read_length']).split('-')
            countsdict['min_length'] = int( rlsplit[0] )
            countsdict['max_length'] = int( rlsplit[-1] )
            del countsdict['read_length']

    return celldict

def main(args):

    L.basicConfig(level=(L.DEBUG if args.debug else L.WARNING))

    all_info = dict()
    # Slurp up all the cells we're going to report on
    for y in args.yamls:
        # Use the special loader that fixes the counts.
        yaml_info = load_cell_yaml(y)

        # Load _blobs and _nanoplot parts.
        if '_blobs' in yaml_info:
            # We now have multiple blobs
            yaml_info['_blobs'] = [ abspath(b, relative_to=y) for b in yaml_info['_blobs'] ]
            yaml_info['_blobs_data'] = [ load_yaml(b) for b in yaml_info['_blobs'] ]
        if '_nanoplot' in yaml_info:
            yaml_info['_nanoplot'] = abspath(yaml_info['_nanoplot'], relative_to=y)
            yaml_info['_nanoplot_data'] = load_yaml(yaml_info['_nanoplot'])
        if '_minknow_report' in yaml_info:
            yaml_info['_minknow_report'] = abspath(yaml_info['_minknow_report'], relative_to=y)

        all_info[yaml_info['Cell']] = yaml_info

    # Glean some pipeline metadata
    if args.pipeline:
        pipedata = get_pipeline_metadata(args.pipeline)
    else:
        pipedata = dict(version=hesiod_version)

    # See if we have some info from the LIMS
    if args.realnames:
        realnames = load_yaml(args.realnames)
    else:
        realnames = None

    # See if we have per-project blob stats. These can't be included in the per-cell YAML
    # files as the combined tables are generated by a separate R script.
    # I've decided to use a single combined metadata file rather than one per project.
    if args.blobstats:
        blobstats = load_blobstats(args.blobstats)
    else:
        blobstats  = None


    # FIXME - we're missing a pipeline status and list of aborted/pending cells?

    rep = format_report( all_info,
                         pipedata = pipedata,
                         aborted_list = [],
                         minionqc = args.minionqc,
                         totalcells = args.totalcells,
                         project_realnames = realnames,
                         blobstats = blobstats )

    if (not args.out) or (args.out == '-'):
        print(*rep, sep="\n")
    else:
        L.info(f"Writing to {args.out}")
        with open(args.out, "w") as ofh:
            print(*rep, sep="\n", file=ofh)

        copy_dest = os.path.dirname(args.out) or '.'
        L.info(f"Copying files to {copy_dest}")

        copy_files(all_info, copy_dest, minionqc=args.minionqc)

def load_blobstats(filename):
    """Load the YAML file but then also add the split_out contents of all of
       the linked CSV files.
    """
    blobstats = load_yaml(filename)

    for proj_stats in blobstats.values():
        for proj_file in proj_stats:
            # proj_file is now a dict which must have a 'tsv' member
            tsv_file = proj_file['tsv']

            # Resolve the file name relative to the original YAML file,
            # as in load_yaml.
            if not tsv_file.startswith('/'):
                tsv_file = os.path.join(os.path.dirname(filename), tsv_file)

            with open(tsv_file) as fh:
                # Naive TSV split is fine
                proj_file['tsv_data'] = [ line.strip().split('\t') for line in fh ]

    return blobstats

def list_projects(cells, realname_dict):
    """ Given a list of cells, which have 'Project' set, come up with a set of headings
        to print and return a list of (name, heading, cells) tuples.
        The list of names will be converted to a sorted set.
    """
    if realname_dict is None:
        realname_dict = dict()

    res = OrderedDict()

    for c in cells:
        n = c['Project']
        if n in res:
            # Just add this cell to the list
            res[n][1].append(c)
        else:
            # Do we know about this one?
            if n in realname_dict:
                title = f"Project {realname_dict[n].get('name')}"
                if realname_dict[n].get('url'):
                    title += f"\n\n[\[Go to project page\]]({realname_dict[n].get('url')})"
            else:
                title = f"Project {n}"
            res[n] = (title, [c])

    # Convert dict of doubles back to list of triples and sort them too
    return [ (k, *v) for k, v in sorted(res.items()) ]

def gen_thumb(afile):
    """Given a filename return the base file and the thumbnail file
    """
    return [re.sub(r'(.*\.|^)(.+)', r'\1__thumb.\2', afile), afile]

def copy_files(all_info, base_path, minionqc=None):
    """ We need to copy the NanoPlot, MinionQC, Blob reports into here.
        Base path will normally be wherever the report is being made.
    """
    # Flush anything that is there already and re-make the image directory
    # Same for the NanoPlot reports
    for dirname in ["img", "np"]:
        try:
            shutil.rmtree(os.path.join(base_path, dirname))
        except FileNotFoundError:
            pass
        os.makedirs(os.path.join(base_path, dirname))

    for cell, ci in sorted(all_info.items()):

        # We're flattening files into a single directory, so need a unique naming scheme.
        # This should work. Hopefully names won't get too long.
        cell_uid = ci['Base'].split('/')[-1]

        # Blobs now come in a list of YAML files
        for ablob in ci.get('_blobs', []):
            blob_base = os.path.dirname(ablob)
            blob_yaml = load_yaml(ablob)

            for pngfile in [ f2 for b in blob_yaml for f1 in b['files'] for f2 in f1 ]:
                for file_or_thumb in gen_thumb(pngfile):
                    png = os.path.join(blob_base, file_or_thumb)
                    dest_png = os.path.basename(png)
                    L.debug(f"Copying {png}")
                    copy_file(png, os.path.join(base_path, "img", dest_png))

        if '_nanoplot' in ci:
            nano_base = os.path.dirname(ci['_nanoplot'])

            src_rep = f"{nano_base}/NanoPlot-report.html"
            dest_rep = f"np/NanoPlot_{cell_uid}-report.html"
            copy_file(src_rep, os.path.join(base_path, dest_rep))

            for png in glob(nano_base + '/*.png'):
                dest_png = f"nanoplot_{cell_uid}_{os.path.basename(png)}"
                copy_file(png, os.path.join(base_path, "img", dest_png))

        if '_minionqc' in ci:
            min_base = os.path.dirname(ci['_minionqc'])

            for png in glob(min_base + '/*.png'):
                dest_png = f"minqc_{cell_uid}_{os.path.basename(png)}"
                copy_file(png, os.path.join(base_path, "img", dest_png))

        if '_minknow_report' in ci:
            rep_base = os.path.dirname(ci['_minknow_report'])
            copy_file( ci['_minknow_report'],
                       os.path.join(base_path, "minknow", os.path.basename(ci['_minknow_report'])) )

    # Combined plots for MinionQC are separate
    if minionqc:
        cmin_base = os.path.dirname(minionqc)
        for png in glob(cmin_base + '/*.png'):
            dest_png = f"minqc_combined_{os.path.basename(png)}"
            copy_file(png, os.path.join(base_path, "img", dest_png))

def get_pipeline_metadata(pipe_dir):
    """ Read the files in the pipeline directory to find out some stuff about the
        pipeline. This is similar to what we get from run_info.py.
    """
    # The start_times file reveals the versions applied
    starts = list()

    try:
        with open(pipe_dir + '/start_times') as fh:
            for l in fh:
                starts.append(l.strip())
    except Exception:
        # Meh.
        pass

    # The upstream location (the file should have one single line but be prepared for junk)
    try:
        with open(pipe_dir + '/upstream') as fh:
            upstream = " ".join([l.strip() for l in fh])
    except FileNotFoundError as e:
        upstream = str(e)


    versions = set([ l.split('@')[0] for l in starts ])
    # Plus there's the current version
    versions.add(hesiod_version)

    # Get the name of the directory what pipe_dir is in
    rundir = os.path.basename( os.path.realpath(pipe_dir + '/..') )

    return dict( version = '+'.join(sorted(versions)),
                 start_times = [ l.split('@')[1] for l in starts ],
                 upstream = upstream,
                 rundir = rundir )

class aggregator:
    """A light wrapper around a list to save some typing when building
       a list of lines to be printed.
    """
    def __init__(self, *args):
        self._list = list()
        if args:
            self(*args)

    def __call__(self, *args):
        self._list.extend([str(a) for a in args] or [''])

    def __iter__(self, *args):
        return iter(self._list)

def escape_md(in_txt, backwhack=re.compile(r'([][\\`*_{}()#+-.!<>])')):
    """ HTML escaping is not the same as markdown escaping
    """
    return re.sub(backwhack, r'\\\1', str(in_txt))

def fixcase(in_txt):
    """ Take a string_like_this and return a String Like This
    """
    return ' '.join(p.capitalize() for p in in_txt.split("_"))

def copy_file(src, dest):
    """ Wrapper around shutil.copyfile that won't clobber the destination file
    """
    if os.path.exists(dest):
        raise FileExistsError(dest)

    return shutil.copyfile(src, dest)

def parse_args(*args):
    description = """ Makes a report (in PanDoc format) for a run (aka an experiment), by compiling the info from the
                      YAML files that are made per-cell.
                  """
    argparser = ArgumentParser( description=description,
                                formatter_class = ArgumentDefaultsHelpFormatter )
    argparser.add_argument("yamls", nargs='*',
                            help="Supply a list of info.yml files to compile into a report.")
    argparser.add_argument("--minionqc",
                           help="Add minionqc combined stats")
    argparser.add_argument("--totalcells",
                            help="Manually set the total number of cells, if not all are yet reported.")
    argparser.add_argument("-p", "--pipeline", default="rundata/pipeline",
                            help="Directory to scan for pipeline meta-data.")
    argparser.add_argument("-r", "--realnames",
                            help="YAML file containing real names for projects.")
    argparser.add_argument("-b", "--blobstats",
                            help="YAML file containing BLOB stats links - normally blobstats_by_project.yaml.")
    argparser.add_argument("-f", "--fudge_status",
                            help="Override the PipelineStatus shown in the report.")
    argparser.add_argument("-o", "--out",
                            help="Where to save the report. Defaults to stdout.")
    argparser.add_argument("-d", "--debug", action="store_true",
                            help="Print more verbose debugging messages.")

    return argparser.parse_args(*args)

if __name__ == "__main__":
    main(parse_args())
