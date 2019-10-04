#!/usr/bin/env python3
import os, sys, re
import logging as L
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from pprint import pformat
from datetime import datetime
from collections import OrderedDict, namedtuple
import yaml, yamlloader
import shutil
import base64

from hesiod import hesiod_version, glob, parse_cell_name, load_yaml

def format_report( all_info,
                   pipedata,
                   aborted_list = (),
                   minionqc = None,
                   totalcells = None ):
    """Makes the report as a list of strings (lines)
    """

    res = []
    P = lambda *a: res.extend(a or [''])

    # Get the run(s)
    runs = sorted(set([ i['Run'] for i in all_info.values() ]))
    instr = sorted(set([ i['Run'].split('_')[1] for i in all_info.values() ]))
    libs = sorted(set([ i['Cell'].split('/')[0] for i in all_info.values() ]))

    # Header
    P( "% Promethion run {}".format(",".join(runs)),
       "% Hesiod version {}".format(pipedata['version']),
       "% {}".format(datetime.now().strftime("%A, %d %b %Y %H:%M")) )

    # Run metadata
    P()
    P( "# About this run (experiment? project?)\n")
    P( "### Metadata\n")
    P( '<dl class="dl-horizontal">' )
    P( '<dt>Run ID</dt> <dd>{}</dd>'.format(",".join(runs)) )
    P( '<dt>Upstream Location</dt> <dd>{}</dd>'.format(pipedata['upstream']) )
    P( '<dt>Instrument</dt> <dd>{}</dd>'.format(",".join(instr)) )
    P( '<dt>Cell Count</dt> <dd>{}</dd>'.format(len(all_info) if totalcells is None else totalcells) )
    P( '<dt>Library Count</dt> <dd>{}</dd>'.format(len(libs)) )
    P( '<dt>Start Time</dt> <dd>{}</dd>'.format((pipedata['start_times'] or ['unknown'])[0]) )
    P( '<dt>Last Run Time</dt> <dd>{}</dd>'.format((pipedata['start_times'] or ['unknown'])[-1]) )
    P( '</dl>' )

    # Overview plots from minionqc/combinedQC
    if minionqc:
        P('\n### {}\n'.format("MinionQC: Combined Length Histo ; Combined Quality Histo ; Combined Yield over Time"))
        P("<div class='flex'>")
        P(" ".join(
            "[plot](img/minqc_combined_{f}.png){{.thumbnail}}".format(f=f)
            for f in ['combined_length_histogram', 'combined_q_histogram', 'yield_over_time']
         ))
        P("</div>")

    for cell, ci in sorted(all_info.items()):
        P()
        P( "# Cell {}".format(cell) )
        P()
        P( ":::::: {.bs-callout}" )

        # Basic cell metadata
        P( '<dl class="dl-horizontal">' )
        P("### Metadata")
        for k, v in ci.items():
            if not k.startswith("_"):
                # Special case for date
                if k == "Date" and re.match(r'[0-9]{8}', v):
                    v = datetime.strptime(v, '%Y%m%d').strftime('%d %b %Y')
                P('<dt>{}</dt> <dd>{}</dd>'.format(k,escape(v)))
        P( '</dl>' )
        P()

        # Stuff from the .count files that's been embedded in the YAML
        for cdata in ci.get('_counts', []):
            P( '<dl class="dl-horizontal">' )
            P("### {}".format(escape(cdata['_label'])))
            for k, v in cdata.items():
                if not k.startswith("_"):
                    P('<dt>{}</dt> <dd>{}</dd>'.format(k,escape(v)))
            P( '</dl>' )
            P()


        # Nanoplot stats
        if '_nanoplot' in ci:
            ns = load_yaml(ci['_nanoplot'])

            ''' # Selective version??
            P("### Nanoplot General summary")
            nsgs, = [ i[1] for i in ns if i[0] == "General summary" ]
            for k, pv, n*_ in nsgs:
                P('<dt>{}</dt> <dd>{}</dd>'.format(k,escape(pv)))
            '''

            for title, items in ns:
                P( '<dl class="dl-horizontal">' )
                P("### Nanoplot {}\n".format(escape(title)))
                for k, pv, *_ in items:
                    P('<dt>{}</dt> <dd>{}</dd>'.format(escape(k),escape(pv)))
                P( '</dl>' )
                P()

        # Embed some files from MinionQC
        if '_minionqc' in ci:
            P('\n### {}\n'.format("MinionQC: Length Histo ; Length vs Qual ; Yield over Time"))
            P("<div class='flex'>")
            P(" ".join(
                "[plot](img/minqc_{ci[Library]}_{ci[CellID]}_{f}.png){{.thumbnail}}".format(ci=ci, f=f)
                for f in ['length_histogram', 'length_vs_q', 'yield_over_time']
             ))
            P("</div>")

        # Nanoplot plots
        if '_nanoplot' in ci:
            P('\n### {}\n'.format("NanoPlot: Length Histo ; Length vs Qual ; Yield over Time"))
            P("<div class='flex'>")
            P(" ".join(
                "[plot](img/nanoplot_{ci[Library]}_{ci[CellID]}_{f}.png){{.thumbnail}}".format(ci=ci, f=f)
                for f in ['HistogramReadlength', 'LengthvsQualityScatterPlot_dot', 'NumberOfReads_Over_Time']
             ))
            P("</div>")


            # Link to the NanoPlot report
            P( "[Full NanoPlot Report](NanoPlot_{ci[Library]}_{ci[CellID]}-report.html)".format(ci=ci) )

        # Blob plots as per SMRTino (the YAML file is linked rather than embedded but it's the
        # same otherwise)
        if '_blobs' in ci:
            for plot_group in load_yaml(ci['_blobs']):

                P('\n### {}\n'.format(plot_group['title']))

                # plot_group['files'] will be a a list of lists, so plot
                # each list a s a row.
                for plot_row in plot_group['files']:
                    P("<div class='flex'>")
                    P(" ".join(
                        "[plot](img/{f}){{.thumbnail}}".format(f=os.path.basename(p))
                        for p in plot_row
                     ))
                    P("</div>")

        P( "::::::" )

    P()
    P("*~~~*")
    return res

def main(args):

    L.basicConfig(level=(L.DEBUG if args.debug else L.WARNING))

    all_info = dict()
    # Basic basic basic
    for y in args.yamls:
        yaml_info = load_yaml(y)

        # Sort by cell ID - all YAML must have this.
        assert yaml_info.get('Cell'), "All yamls must have a Cell ID"

        all_info[yaml_info['Cell']] = yaml_info

    # Glean some pipeline metadata
    if args.pipeline:
        pipedata = get_pipeline_metadata(args.pipeline)
    else:
        pipedata = dict(version=hesiod_version)

    # FIXME - we're missing a pipeline status and list of aborted/pending cells?

    rep = format_report( all_info,
                         pipedata = pipedata,
                         aborted_list = [],
                         minionqc = args.minionqc,
                         totalcells = args.totalcells )

    if (not args.out) or (args.out == '-'):
        print(*rep, sep="\n")
    else:
        L.info("Writing to {}".format(args.out))
        with open(args.out, "w") as ofh:
            print(*rep, sep="\n", file=ofh)

        copy_dest = os.path.dirname(args.out) or '.'
        L.info("Copying files to {}".format(copy_dest))

        copy_files(all_info, copy_dest, minionqc=args.minionqc)

def copy_files(all_info, base_path, minionqc=None):
    """ We need to copy the NanoPlot, MinionQC, Blob reports into here.
        Base path will normally be wherever the report is being made.
    """
    os.makedirs(os.path.join(base_path, "img") , exist_ok=True)

    for cell, ci in sorted(all_info.items()):

        if '_blobs' in ci:
            blob_base = os.path.dirname(ci['_blobs'])

            for png in glob(blob_base + '/*.png'):
                dest_png = os.path.basename(png)
                shutil.copy(png, os.path.join(base_path, "img", dest_png))

        if '_nanoplot' in ci:
            nano_base = os.path.dirname(ci['_nanoplot'])

            src_rep = "{nb}/NanoPlot-report.html".format(nb=nano_base)
            dest_rep = "NanoPlot_{ci[Library]}_{ci[CellID]}-report.html".format(ci=ci)
            shutil.copy(src_rep, os.path.join(base_path, dest_rep))

            for png in glob(nano_base + '/*.png'):
                dest_png = "nanoplot_{ci[Library]}_{ci[CellID]}_{f}".format(ci=ci, f=os.path.basename(png))
                shutil.copy(png, os.path.join(base_path, "img", dest_png))

        if '_minionqc' in ci:
            min_base = os.path.dirname(ci['_minionqc'])

            for png in glob(min_base + '/*.png'):
                dest_png = "minqc_{ci[Library]}_{ci[CellID]}_{f}".format(ci=ci, f=os.path.basename(png))
                shutil.copy(png, os.path.join(base_path, "img", dest_png))

    # Combined plots for MinionQC are separate
    if minionqc:
        cmin_base = os.path.dirname(minionqc)
        for png in glob(cmin_base + '/*.png'):
            dest_png = "minqc_combined_{f}".format(f=os.path.basename(png))
            shutil.copy(png, os.path.join(base_path, "img", dest_png))

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

def escape(in_txt, backwhack=re.compile(r'([][\`*_{}()#+-.!<>])')):
    """ HTML escaping is not the same as markdown escaping
    """
    return re.sub(backwhack, r'\\\1', str(in_txt))

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
    argparser.add_argument("-f", "--fudge_status",
                            help="Override the PipelineStatus shown in the report.")
    argparser.add_argument("-o", "--out",
                            help="Where to save the report. Defaults to stdout.")
    argparser.add_argument("-d", "--debug", action="store_true",
                            help="Print more verbose debugging messages.")

    return argparser.parse_args(*args)

if __name__ == "__main__":
    main(parse_args())
